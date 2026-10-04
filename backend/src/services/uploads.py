"""Uploading a video a piece at a time.

A 500 MB file sent as one request fails entirely on any dropped
connection, and forces the gateway to accept a body that large from
anyone who asks. Uploading in parts costs one part on a drop, and no
single request is ever bigger than a part.

The shape is S3's multipart upload, which is what storage underneath
offers anyway:

    POST   /api/files/uploads                 start, get an id
    PUT    /api/files/uploads/{id}/parts/{n}  send one part
    GET    /api/files/uploads/{id}            what has arrived (resume)
    POST   /api/files/uploads/{id}/complete   assemble, then the metadata
    DELETE /api/files/uploads/{id}            give up

Two things are deliberately not taken on trust. Which parts have arrived
is asked of storage rather than recorded here -- storage decides whether
a part exists, and a row that disagreed with it would resume into a
corrupt file. And the hash is computed by the server from the assembled
object, because it decides whether the upload is a duplicate: a
client-supplied hash would be the client deciding.

No video row exists until completion. The single-shot path committed the
row first and uploaded afterwards, so a storage failure left a row stuck
in "queued" that its owner could not delete and whose hash blocked them
from ever re-uploading their own file.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional
from uuid import UUID

import xxhash
from fastapi import UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors.uploads import (
    PartTooSmallError,
    UploadNotFoundError,
    UploadSizeMismatchError,
)
from src.models.upload_session import UploadSession
from src.schemas.uploads import UploadSessionStatus, UploadStarted

if TYPE_CHECKING:
    from src.infrastructure.s3_client import S3Client
    from src.services.files import FileService

#: S3 requires every part except the last to be at least 5 MiB, so that
#: is the floor whatever the client would prefer.
MIN_PART_BYTES = 5 * 1024 * 1024

#: What the client is told to use. Large enough that a 500 MB upload is
#: 50 requests rather than 500, small enough that losing one costs little.
PART_SIZE = 10 * 1024 * 1024

#: S3 allows 10 000 parts; with the part size above that is far more than
#: the size limit allows, so it is a sanity bound rather than a real one.
MAX_PARTS = 10_000

#: An upload nobody has touched for this long is abandoned. The parts it
#: holds take up space and appear in no object listing, so they have to
#: be swept rather than waited on.
SESSION_TTL = timedelta(hours=24)


class UploadService:
    def __init__(
        self,
        session: AsyncSession,
        s3_client: "S3Client",
        file_service: "FileService",
    ):
        self.session = session
        self.s3_client = s3_client
        self.file_service = file_service

    # ── Starting ──────────────────────────────────────────────────────

    async def start(
        self, *, user_id: UUID, filename: str, content_type: str, size: int
    ) -> UploadStarted:
        """Reserve a video id and open a multipart upload against it."""
        if not (content_type or "").startswith("video/"):
            from src.errors.files import InvalidVideoFormatError

            raise InvalidVideoFormatError()

        # Checked here as a claim, and again at completion against the
        # assembled object -- otherwise a client could declare 1 MB and
        # send 2 GB.
        await self.file_service._check_video_size(size)

        video_id = uuid.uuid4()
        suffix = ("." + filename.rsplit(".", 1)[-1]) if "." in filename else ""
        object_key = f"{video_id}{suffix}"

        storage_upload_id = await self.s3_client.begin_multipart(
            object_key, bucket_name="videos"
        )

        record = UploadSession(
            user_id=user_id,
            video_id=video_id,
            object_key=object_key,
            storage_upload_id=storage_upload_id,
            filename=filename,
            content_type=content_type,
            declared_size=size,
        )
        self.session.add(record)
        await self.session.commit()

        return UploadStarted(
            upload_id=record.id,
            part_size=PART_SIZE,
            total_parts=max(1, -(-size // PART_SIZE)),
        )

    # ── Sending parts ─────────────────────────────────────────────────

    async def upload_part(
        self, *, upload_id: UUID, user_id: UUID, part_number: int, body: bytes
    ) -> UploadSessionStatus:
        record = await self._owned_session(upload_id, user_id)

        if not 1 <= part_number <= MAX_PARTS:
            raise PartTooSmallError(f"part number must be between 1 and {MAX_PARTS}")

        # The last part may be short; any other short part would make the
        # assembled object unreadable, and S3 only says so at completion
        # -- by which time the whole upload is lost.
        is_last = part_number * PART_SIZE >= record.declared_size
        if len(body) < MIN_PART_BYTES and not is_last:
            raise PartTooSmallError(
                f"part {part_number} is {len(body)} bytes; all but the last "
                f"must be at least {MIN_PART_BYTES}"
            )

        await self.s3_client.upload_part(
            record.object_key,
            "videos",
            record.storage_upload_id,
            part_number,
            body,
        )
        # Touched so the sweeper can tell a slow upload from an abandoned
        # one.
        record.updated_at = datetime.now(timezone.utc)
        await self.session.commit()

        return await self.status(upload_id=upload_id, user_id=user_id)

    # ── Resuming ──────────────────────────────────────────────────────

    async def status(self, *, upload_id: UUID, user_id: UUID) -> UploadSessionStatus:
        """What storage holds, so a client can send only what is missing."""
        record = await self._owned_session(upload_id, user_id)
        parts = await self.s3_client.list_parts(
            record.object_key, "videos", record.storage_upload_id
        )
        return UploadSessionStatus(
            upload_id=record.id,
            part_size=PART_SIZE,
            declared_size=record.declared_size,
            received_parts=[p["PartNumber"] for p in parts],
            received_bytes=sum(p["Size"] for p in parts),
        )

    # ── Finishing ─────────────────────────────────────────────────────

    async def complete(
        self,
        *,
        upload_id: UUID,
        user_id: UUID,
        name: str,
        description: str,
        privacy: str,
        category: str,
        thumbnail: Optional[UploadFile],
    ):
        """Assemble the parts, then do what the old upload did at the end.

        The video row, the duplicate check and the encode job all happen
        here -- after the bytes are stored, not before.
        """
        record = await self._owned_session(upload_id, user_id)

        parts = await self.s3_client.list_parts(
            record.object_key, "videos", record.storage_upload_id
        )
        if not parts:
            raise UploadSizeMismatchError("no parts were received")

        await self.s3_client.complete_multipart(
            record.object_key, "videos", record.storage_upload_id, parts
        )

        try:
            video_hash, actual_size = await self._hash_stored_object(record.object_key)

            # The declared size was a claim; this is the file.
            if actual_size != record.declared_size:
                raise UploadSizeMismatchError(
                    f"declared {record.declared_size} bytes, stored {actual_size}"
                )
            await self.file_service._check_video_size(actual_size)

            response = await self.file_service.register_uploaded_video(
                video_id=record.video_id,
                object_key=record.object_key,
                video_hash=video_hash,
                size=actual_size,
                name=name,
                description=description,
                privacy=privacy,
                category=category,
                user_id=user_id,
                thumbnail=thumbnail,
            )
        except Exception:
            # Nothing references the object once the session row is gone,
            # so it would be orphaned bytes that no listing explains.
            await self._discard_object(record.object_key)
            await self._forget(record)
            raise

        await self._forget(record)
        return response

    async def abort(self, *, upload_id: UUID, user_id: UUID) -> None:
        """Give up on an upload and release the parts it holds."""
        record = await self._owned_session(upload_id, user_id)
        await self.s3_client.abort_multipart(
            record.object_key, "videos", record.storage_upload_id
        )
        await self._forget(record)

    async def sweep_abandoned(self) -> int:
        """Drop sessions nobody has touched for a day.

        An unfinished multipart upload keeps every part already sent and
        shows up in no object listing, so the space is spent and
        invisible until something aborts it.
        """
        cutoff = datetime.now(timezone.utc) - SESSION_TTL
        rows = await self.session.execute(
            select(UploadSession).where(UploadSession.updated_at < cutoff)
        )
        stale = list(rows.scalars())
        for record in stale:
            await self.s3_client.abort_multipart(
                record.object_key, "videos", record.storage_upload_id
            )
            await self.session.execute(
                delete(UploadSession).where(UploadSession.id == record.id)
            )
        if stale:
            await self.session.commit()
            logging.info("Swept %d abandoned upload sessions", len(stale))
        return len(stale)

    # ── Internals ─────────────────────────────────────────────────────

    async def _owned_session(self, upload_id: UUID, user_id: UUID) -> UploadSession:
        result = await self.session.execute(
            select(UploadSession).where(
                UploadSession.id == upload_id,
                # Ownership is the where clause: a session belonging to
                # somebody else is simply not found, so the endpoint does
                # not confirm that the id exists.
                UploadSession.user_id == user_id,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise UploadNotFoundError()
        return record

    async def _hash_stored_object(self, object_key: str) -> tuple[str, int]:
        """Hash and size, read back from storage.

        The same xxh3_128 the single-shot path used, so a file uploaded
        either way produces the same hash and the duplicate rule keeps
        meaning one thing.
        """
        hasher = xxhash.xxh3_128()
        size = 0
        async for chunk in self.s3_client.iter_object(object_key, "videos"):
            hasher.update(chunk)
            size += len(chunk)
        return hasher.hexdigest(), size

    async def _discard_object(self, object_key: str) -> None:
        """Release the stored object, bytes and all.

        Every version, not just the current one: the bucket is versioned,
        so a plain delete leaves the file behind as a noncurrent version.
        A refused upload is an ordinary thing -- a duplicate file, a size
        that does not match -- so leaving a copy each time is a steady
        leak nothing would explain.
        """
        try:
            await self.s3_client.delete_all_versions(object_key, "videos")
        except Exception:  # noqa: BLE001 - best effort, the caller is already failing
            logging.warning("Could not remove %s after a failed upload", object_key)

    async def _forget(self, record: UploadSession) -> None:
        await self.session.execute(
            delete(UploadSession).where(UploadSession.id == record.id)
        )
        await self.session.commit()
