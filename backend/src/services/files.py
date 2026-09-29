import logging
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from uuid import NAMESPACE_DNS, UUID, uuid4, uuid5

import xxhash
from aio_pika.exceptions import AMQPException
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import UploadFile
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.status_ids import (
    STATUS_FAILED_ID,
    STATUS_QUEUED_ID,
    STATUS_READY_ID,
    privacy_id_for,
)
from src.errors.files import (
    ChannelNotFoundError,
    DuplicateVideoError,
    EmptyFileError,
    FileTooLargeError,
    InvalidThumbnailFormatError,
    InvalidVideoFormatError,
    JobPublishFailedError,
    ResolutionNotFoundError,
    S3DeletionError,
    S3DownloadError,
)
from src.errors.videos import VideoNotFoundError
from src.models.channel import Channel
from src.models.user import User
from src.models.video import Video
from src.models.video_resolutions import VideoResolution
from src.schemas.endpoint import FileMeta, FileResponse

if TYPE_CHECKING:
    from faststream.rabbit import RabbitBroker

    from src.infrastructure.s3_client import S3Client


async def _hash_and_size(uploaded_file: UploadFile) -> tuple[str, int]:
    hasher = xxhash.xxh3_128()
    block_size = 1024 * 1024

    await uploaded_file.seek(0)
    size = 0

    # hash + size in one pass
    while chunk := await uploaded_file.read(block_size):
        hasher.update(chunk)
        size += len(chunk)
    await uploaded_file.seek(0)
    return hasher.hexdigest(), size


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

    async def _get_channel_id(self, user_id: UUID) -> UUID:
        result = await self.session.execute(
            select(Channel.id).where(Channel.user_id == user_id)
        )
        channel_id = result.scalar_one_or_none()

        if not channel_id:
            user_result = await self.session.execute(
                select(User.username).where(User.id == user_id)  # type: ignore[arg-type]
            )
            username = user_result.scalar_one_or_none()
            if not username:
                raise ChannelNotFoundError()
            channel = Channel(user_id=user_id, name=username)
            self.session.add(channel)
            await self.session.flush()
            channel_id = channel.id

        return channel_id

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

    async def _upload_video_file(self, video_id: UUID, video: UploadFile) -> str:
        video_suffix = Path(video.filename or "").suffix
        new_filename = f"{video_id}{video_suffix}"
        await self.s3_client.upload_file(new_filename, video.file, bucket_name="videos")
        return new_filename

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
                category_id=uuid5(NAMESPACE_DNS, f"video_category:{category.lower()}"),
                status_id=STATUS_QUEUED_ID,
            )
            .on_conflict_do_nothing(index_elements=["hash"])
            .returning(Video.id)
        )
        inserted_id = result.scalar_one_or_none()
        await self.session.commit()
        return inserted_id

    async def upload_video(
        self,
        *,
        video: UploadFile,
        thumbnail: UploadFile | None,
        name: str,
        description: str,
        privacy: str,
        category: str,
        user_id: UUID,
    ) -> FileResponse:

        if not (video.content_type or "").startswith("video/"):
            raise InvalidVideoFormatError()

        if thumbnail and not (thumbnail.content_type or "").startswith("image/"):
            raise InvalidThumbnailFormatError()

        video_hash, video_size = await _hash_and_size(video)
        await self._check_video_size(video_size)
        video_id = uuid.uuid4()

        channel_id = await self._get_channel_id(user_id)

        inserted = await self._insert_video(
            video_id,
            name,
            description,
            channel_id,
            video_size,
            video_hash,
            privacy,
            category,
        )

        if not inserted:
            raise DuplicateVideoError()

        if thumbnail:
            await self._upload_thumbnail(video_id, thumbnail)

        filename = await self._upload_video_file(video_id, video)

        try:
            if self.broker is None:
                raise RuntimeError("Broker is not configured")

            await self.broker.publish(
                filename,
                queue="video.encode",
                priority=10,
            )
        except (RuntimeError, AMQPException, OSError) as e:
            # Compensate: a video row with no encode job would sit in "queued"
            # forever, so the upload is rolled back whatever the cause.
            logging.error(f"Upload pipeline failed for {video_id}: {e}")

            await self.session.execute(delete(Video).where(Video.id == video_id))
            await self.session.commit()
            raise JobPublishFailedError() from e

        return FileResponse(
            status="accepted",
            files=[
                FileMeta(
                    file_id=video_id,
                    filename=name,
                    size=video_size,
                )
            ],
        )

    async def get_video_file(
        self, video_id: UUID, user_id: UUID, resolution: Optional[str] = None
    ) -> tuple[str, str, str]:
        """Return (object_key, filename, media_type) for streaming"""
        result = await self.session.execute(
            select(Video)
            .join(Channel, Channel.id == Video.channel_id)
            .where(Video.id == video_id, Channel.user_id == user_id)
        )
        video = result.scalar_one_or_none()
        if not video:
            raise VideoNotFoundError()

        if resolution:
            target_height = int(resolution.rstrip("p"))
            res_result = await self.session.execute(
                select(VideoResolution).where(
                    (VideoResolution.video_id == video_id)
                    & (VideoResolution.height == target_height)
                )
            )
            res_obj = res_result.scalar_one_or_none()
            if not res_obj:
                raise ResolutionNotFoundError(resolution)
            object_key = res_obj.playlist_path.lstrip("/")
            filename = f"{video.name}_{res_obj.height}p.m3u8"
            media_type = "application/vnd.apple.mpegurl"
        else:
            # Default/original file
            object_key = str(video.id)
            filename = f"{video.name}.mp4"
            media_type = "video/mp4"

        return object_key, filename, media_type

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
                await self.s3_client.delete_file(
                    thumbnail_path.split("/")[-1], bucket_name="video-thumbnails"
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
                await self.s3_client.delete_file(key, bucket_name="videos")
