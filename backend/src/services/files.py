import logging
import re
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from aio_pika.exceptions import AMQPException
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import UploadFile
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.status_ids import (
    STATUS_FAILED_ID,
    STATUS_QUEUED_ID,
    STATUS_READY_ID,
    category_id_for,
    privacy_id_for,
)
from src.errors.files import (
    AlreadyUploadedError,
    ChannelNameUnavailableError,
    ChannelNotFoundError,
    DownloadNotReadyError,
    DownloadUnavailableError,
    DuplicateVideoError,
    EmptyFileError,
    FileTooLargeError,
    InvalidThumbnailFormatError,
    JobPublishFailedError,
    S3DeletionError,
    S3DownloadError,
)
from src.errors.videos import VideoNotFoundError
from src.models.channel import Channel
from src.models.user import User
from src.models.video import Video
from src.schemas.endpoint import FileMeta, FileResponse

if TYPE_CHECKING:
    from faststream.rabbit import RabbitBroker

    from src.infrastructure.s3_client import S3Client


class FileService:
    def __init__(
        self,
        session: AsyncSession,
        s3_client: "S3Client",
        broker: Optional["RabbitBroker"] = None,
    ):
        self.session = session
        self.s3_client = s3_client
        self.broker = broker
        self.MAX_VIDEO_BYTES = 500_000_000  # 500MB

    #: How many times to try a suffixed name before giving up. Each
    #: attempt is a round trip, and anyone whose username collides this
    #: many times is better served by picking a channel name themselves.
    CHANNEL_NAME_ATTEMPTS = 20

    async def _get_channel_id(self, user_id: UUID) -> UUID:
        """The uploader's channel, created on first upload if they have none.

        Channel.name is unique across the platform, and the name taken
        here is the username -- so a user whose name somebody else had
        already used as a channel name hit an IntegrityError and a 500,
        on their first upload, with nothing explaining why. The two names
        are separate things and nothing stops them colliding.
        """
        result = await self.session.execute(
            select(Channel.id).where(Channel.user_id == user_id)
        )
        channel_id = result.scalar_one_or_none()
        if channel_id:
            return channel_id

        user_result = await self.session.execute(
            select(User.username).where(User.id == user_id)  # type: ignore[arg-type]
        )
        username = user_result.scalar_one_or_none()
        if not username:
            raise ChannelNotFoundError()

        return await self._create_channel(user_id, str(username))

    async def _create_channel(self, user_id: UUID, username: str) -> UUID:
        """Create the channel, working around a name already in use.

        A savepoint per attempt: an IntegrityError poisons the
        transaction, and without one the first collision would take the
        whole upload down with it -- including the video row the caller
        is about to write.
        """
        for attempt in range(self.CHANNEL_NAME_ATTEMPTS):
            name = username if attempt == 0 else f"{username}-{attempt + 1}"
            try:
                async with self.session.begin_nested():
                    channel = Channel(user_id=user_id, name=name)
                    self.session.add(channel)
                    await self.session.flush()
                if attempt:
                    logging.info(
                        "Channel name %r was taken; used %r instead", username, name
                    )
                return channel.id
            except IntegrityError:
                # Either the name is taken, or another request created
                # this user's channel a moment ago. Both are ordinary.
                existing = await self.session.execute(
                    select(Channel.id).where(Channel.user_id == user_id)
                )
                mine = existing.scalar_one_or_none()
                if mine:
                    return mine

        raise ChannelNameUnavailableError()

    async def _upload_thumbnail(self, video_id: UUID, thumbnail: UploadFile) -> None:
        thumb_suffix = Path(thumbnail.filename or "").suffix
        thumbnail_id = str(uuid4())
        thumb_name = f"{thumbnail_id}{thumb_suffix}"
        await self.s3_client.upload_file(
            thumb_name, thumbnail.file, bucket_name="video-thumbnails"
        )
        await self.session.execute(
            update(Video)
            .where(Video.id == video_id)
            .values(thumbnail_path=f"/minio/video-thumbnails/{thumb_name}")
        )
        await self.session.commit()

    async def _check_video_size(self, size: int) -> None:
        if size <= 0:
            logging.warning("Empty video file")
            raise EmptyFileError()
        if size > self.MAX_VIDEO_BYTES:
            max_size_mb = self.MAX_VIDEO_BYTES // (1024 * 1024)
            logging.warning(f"Video size {size} exceeds limit {self.MAX_VIDEO_BYTES}")
            raise FileTooLargeError(max_size_mb)

    async def _insert_video(
        self,
        video_id: UUID,
        name: str,
        description: str,
        channel_id: UUID,
        video_size: int,
        video_hash: str,
        privacy: str,
        category: str,
    ) -> UUID | None:
        result = await self.session.execute(
            insert(Video)
            .values(
                id=video_id,
                name=name,
                description=description,
                channel_id=channel_id,
                size=video_size,
                hash=video_hash,
                video_path=None,
                thumbnail_path=None,
                privacy_id=privacy_id_for(privacy),
                category_id=category_id_for(category),
                status_id=STATUS_QUEUED_ID,
            )
            .on_conflict_do_nothing(index_elements=["hash"])
            .returning(Video.id)
        )
        inserted_id = result.scalar_one_or_none()
        await self.session.commit()
        return inserted_id

    #: How long a video may sit in "queued" before its hash is treated as
    #: abandoned. The encoder picks a job up in seconds; a row still queued
    #: after this never got one -- the storage upload or the publish died
    #: after the row was committed. Long enough that a genuine concurrent
    #: upload of the same file is never mistaken for wreckage.
    STALE_QUEUE_GRACE = timedelta(minutes=15)

    async def _video_with_hash(self, video_hash: str) -> Video | None:
        """The existing row that owns this hash, with its channel loaded."""
        result = await self.session.execute(
            select(Video, Channel.user_id)
            .join(Channel, Channel.id == Video.channel_id)
            .where(Video.hash == video_hash)
        )
        row = result.first()
        if row is None:
            return None
        video, owner_id = row
        # Carried alongside rather than looked up again by the caller.
        video.__dict__["_owner_id"] = owner_id
        return video

    def _is_abandoned(self, existing: Video) -> bool:
        """Is this row wreckage holding a hash nobody can use?

        A failed encode is finished and will not change on its own. A row
        still queued past the grace period never reached the encoder at
        all: `_insert_video` commits before the file is uploaded, so a
        storage failure leaves exactly this -- a row the owner cannot
        delete and a hash that blocks them re-uploading their own file
        for good.
        """
        if existing.status_id == STATUS_FAILED_ID:
            return True
        if existing.status_id != STATUS_QUEUED_ID:
            return False
        created = existing.created_at
        if created is None:
            return True
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - created > self.STALE_QUEUE_GRACE

    async def _reclaim(self, existing: Video) -> None:
        """Delete the dead row and anything it left in storage."""
        logging.info(
            "Reclaiming an abandoned video row so its hash can be reused",
            extra={"video_id": str(existing.id)},
        )
        try:
            await self.s3_client.delete_prefix(f"{existing.id}/", bucket_name="videos")
            await self._delete_original_upload(existing)
        except (BotoCoreError, ClientError, S3DeletionError) as e:
            # The row is the thing blocking the re-upload; leftover bytes
            # are the orphan sweeper's problem, not this request's.
            logging.warning(
                f"Could not clear storage for reclaimed video {existing.id}: {e}"
            )
        await self.session.execute(delete(Video).where(Video.id == existing.id))
        await self.session.commit()

    async def register_uploaded_video(
        self,
        *,
        video_id: UUID,
        object_key: str,
        video_hash: str,
        size: int,
        name: str,
        description: str,
        privacy: str,
        category: str,
        user_id: UUID,
        thumbnail: UploadFile | None,
    ) -> FileResponse:
        """Create the video for a file that is already in storage.

        This used to be the tail of a single-shot upload that committed
        the row *before* sending the bytes -- so a storage failure left a
        row stuck in "queued" that its owner could not delete and whose
        hash blocked them from re-uploading their own file. The bytes
        arrive first now, in parts, and nothing exists in the database
        until they are all there.
        """
        if thumbnail and not (thumbnail.content_type or "").startswith("image/"):
            raise InvalidThumbnailFormatError()

        channel_id = await self._get_channel_id(user_id)

        inserted = await self._insert_video(
            video_id,
            name,
            description,
            channel_id,
            size,
            video_hash,
            privacy,
            category,
        )

        if not inserted:
            # One file, one video on the platform -- the rule, not an
            # accident of the unique index. What differs is who is told
            # what, and whether the hash is really still in use.
            existing = await self._video_with_hash(video_hash)
            if existing is None:
                # Removed between the insert and this lookup; the file is
                # free again, so let the caller try once more rather than
                # refuse something that is no longer true.
                raise DuplicateVideoError()

            own = existing.__dict__.get("_owner_id") == user_id

            if own and self._is_abandoned(existing):
                await self._reclaim(existing)
                inserted = await self._insert_video(
                    video_id,
                    name,
                    description,
                    channel_id,
                    size,
                    video_hash,
                    privacy,
                    category,
                )
                if not inserted:
                    raise DuplicateVideoError()
            elif own:
                raise AlreadyUploadedError()
            else:
                # Nothing about the other video is revealed -- not its id,
                # not its channel, not whether it is public.
                raise DuplicateVideoError()

        if thumbnail:
            await self._upload_thumbnail(video_id, thumbnail)

        try:
            if self.broker is None:
                raise RuntimeError("Broker is not configured")

            await self.broker.publish(
                object_key,
                queue="video.encode",
                priority=10,
            )
        except (RuntimeError, AMQPException, OSError) as e:
            # Compensate: a video row with no encode job would sit in
            # "queued" for ever, so the row is rolled back whatever the
            # cause. The stored object is the caller's to clean up -- it
            # is the one that put it there.
            logging.error(f"Could not queue encoding for {video_id}: {e}")

            await self.session.execute(delete(Video).where(Video.id == video_id))
            await self.session.commit()
            raise JobPublishFailedError() from e

        return FileResponse(
            status="accepted",
            files=[FileMeta(file_id=video_id, filename=name, size=size)],
        )

    #: Written by the converter beside the playlists, once, at encode time.
    DOWNLOAD_KEY = "download.mp4"

    async def get_video_file(
        self, video_id: UUID, user_id: UUID
    ) -> tuple[str, str, str]:
        """Return (object_key, filename, media_type) for the download.

        There is one downloadable file per video and the converter builds
        it: a 720p MP4 remuxed from the rendition it already produced.

        Both earlier routes were broken, which is why neither was ever
        reported. Asked for a resolution this returned the .m3u8 playlist
        with a .mp4 filename -- a few hundred bytes of text saved as a
        video. Asked for the original it looked up the key
        ``str(video.id)``, while the upload is stored as ``<id><suffix>``
        and is deleted by the converter the moment the encode succeeds.

        Only the owner reaches this: the join on the channel is the
        authorisation, and it was already here.
        """
        result = await self.session.execute(
            select(Video)
            .join(Channel, Channel.id == Video.channel_id)
            .where(Video.id == video_id, Channel.user_id == user_id)
        )
        video = result.scalar_one_or_none()
        if not video:
            raise VideoNotFoundError()

        if video.status_id != STATUS_READY_ID:
            # Saying "not found" for a video the owner is looking at in
            # Studio, labelled Processing, explains nothing.
            raise DownloadNotReadyError()

        object_key = f"{video.id}/{self.DOWNLOAD_KEY}"
        if not await self.s3_client.list_keys(object_key, bucket_name="videos"):
            # Encoded before the converter built these, or the remux
            # failed and the encode was allowed to stand.
            raise DownloadUnavailableError()

        # Characters Windows and macOS refuse in a filename, and the
        # quote that would end the Content-Disposition header early.
        # The replacements are stripped too: a title made only of slashes
        # would otherwise be handed over as "_.mp4".
        safe_name = (
            re.sub(r'[\\/:*?"<>|\r\n]+', "_", video.name).strip(" ._") or "video"
        )
        return object_key, f"{safe_name}.mp4", "video/mp4"

    def stream_file(
        self,
        object_key: str,
        bucket_name: str = "videos",
        chunk_size: int = 1024 * 1024 * 3,
    ) -> AsyncGenerator[bytes, None]:
        """Returns a generator for StreamingResponse"""
        try:
            return self.s3_client.download_file(
                object_key, chunk_size, bucket_name=bucket_name
            )
        except (BotoCoreError, ClientError) as e:
            logging.error(f"S3 streaming error for {object_key}: {e}")
            raise S3DownloadError(object_key) from e

    async def delete_video(self, video_id: UUID, user_id: UUID) -> Video:
        """Remove a video and everything it put in storage.

        Deleting used to leave every byte behind. It removed the key
        ``str(video.id)`` -- the original upload is stored as
        ``<id><suffix>``, so that key matched nothing -- and never touched
        the transcoded tree under ``<id>/``, which is the bulk of it:
        master playlist, one playlist per rendition and every segment. The
        client has had a ``delete_prefix`` for exactly this since it was
        written, and nothing called it.

        It also refused anything that was not ``ready``, so a video whose
        encode failed could be seen in Studio, labelled Failed, and never
        removed. Only a video still being worked on is held back now,
        because the encoder is writing into that prefix.
        """
        result = await self.session.execute(
            select(Video)
            .join(Channel, Channel.id == Video.channel_id)
            .where(
                Video.id == video_id,
                Channel.user_id == user_id,
                Video.status_id.in_((STATUS_READY_ID, STATUS_FAILED_ID)),
            )
        )
        video = result.scalar_one_or_none()
        if not video:
            # No rollback here: nothing has been changed yet, and discarding
            # the caller's transaction on a lookup miss throws away whatever
            # else it had pending.
            raise VideoNotFoundError()

        thumbnail_path = (
            video.thumbnail_path.lstrip("/") if video.thumbnail_path else None
        )

        try:
            # The transcoded output: master playlist, per-rendition
            # playlists and every segment.
            await self.s3_client.delete_prefix(f"{video.id}/", bucket_name="videos")
            # The original upload, if the encoder has not removed it
            # already. It keeps the extension it was uploaded with, which
            # the old code left off.
            await self._delete_original_upload(video)
            if thumbnail_path:
                # Every version here too: a deleted video whose preview
                # image is still being served is the same mistake in
                # miniature.
                await self.s3_client.delete_all_versions(
                    thumbnail_path.split("/")[-1], "video-thumbnails"
                )
        except (S3DeletionError, BotoCoreError, ClientError) as e:
            logging.warning(f"S3 deletion failed for {video_id}: {e}")
            await self.session.rollback()
            raise S3DeletionError() from e

        # Delete DB record
        await self.session.delete(video)
        await self.session.commit()
        return video

    async def _delete_original_upload(self, video: Video) -> None:
        """Remove the uploaded source file, whatever extension it carries.

        The convertor deletes it once an encode succeeds, so for most
        videos there is nothing here; for one that failed, this is the
        only copy and it is what the old key never matched.
        """
        prefix = str(video.id)
        for key in await self.s3_client.list_keys(prefix, bucket_name="videos"):
            if "/" not in key[len(prefix) :]:
                await self.s3_client.delete_all_versions(key, "videos")
