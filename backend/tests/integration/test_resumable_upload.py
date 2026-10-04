"""
Real-Postgres tests for uploading a video in parts.

A 500 MB file sent as one request fails entirely on any dropped
connection, and forced the gateway to accept a body that large from
anyone who asked. Uploading in parts costs one part on a drop.

Storage is mocked -- these are about the rules around it: who may touch
an upload, what is taken on trust, and what happens to the bytes when
something goes wrong. The two claims a client makes, the size and which
parts arrived, are both checked against the real thing.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors.files import InvalidVideoFormatError
from src.errors.uploads import (
    PartTooSmallError,
    UploadNotFoundError,
    UploadSizeMismatchError,
)
from src.models.upload_session import UploadSession
from src.services.files import FileService
from src.services.uploads import MIN_PART_BYTES, PART_SIZE, UploadService
from tests.integration.conftest import make_channel, make_user

pytestmark = pytest.mark.integration

FILE_SIZE = 3 * PART_SIZE


def _s3(stored: bytes = b"", parts=None):
    s3 = AsyncMock()
    s3.begin_multipart = AsyncMock(return_value="storage-upload-1")
    s3.upload_part = AsyncMock(return_value='"etag"')
    s3.list_parts = AsyncMock(return_value=list(parts or []))
    s3.complete_multipart = AsyncMock()
    s3.abort_multipart = AsyncMock()
    s3.delete_file = AsyncMock()
    s3.delete_all_versions = AsyncMock(return_value=1)

    async def _iter(key, bucket, chunk_size=1024 * 1024):
        yield stored

    s3.iter_object = _iter
    return s3


def _service(session: AsyncSession, s3) -> UploadService:
    broker = AsyncMock()
    broker.publish = AsyncMock()
    return UploadService(session, s3, FileService(session, s3, broker))


def _part(number: int, size: int = PART_SIZE):
    return {"PartNumber": number, "ETag": f'"etag{number}"', "Size": size}


async def _started(session: AsyncSession, s3, *, size: int = FILE_SIZE):
    user = await make_user(session)
    await make_channel(session, user)
    service = _service(session, s3)
    started = await service.start(
        user_id=user.id, filename="clip.mp4", content_type="video/mp4", size=size
    )
    return user, service, started


class TestStarting:
    @pytest.mark.asyncio
    async def test_it_reports_how_to_send_the_file(self, session: AsyncSession):
        _, _, started = await _started(session, _s3())

        assert started.part_size == PART_SIZE
        assert started.total_parts == 3

    @pytest.mark.asyncio
    async def test_the_parts_are_written_to_the_key_the_video_will_use(
        self, session: AsyncSession
    ):
        """Completing then needs no copy of a half-gigabyte object."""
        s3 = _s3()
        _, _, started = await _started(session, s3)

        record = await session.scalar(
            select(UploadSession).where(UploadSession.id == started.upload_id)
        )
        key = s3.begin_multipart.await_args.args[0]
        assert key.startswith(str(record.video_id))
        assert key.endswith(".mp4")

    @pytest.mark.asyncio
    async def test_something_that_is_not_a_video_never_opens_an_upload(
        self, session: AsyncSession
    ):
        user = await make_user(session)
        s3 = _s3()

        with pytest.raises(InvalidVideoFormatError):
            await _service(session, s3).start(
                user_id=user.id,
                filename="payload.exe",
                content_type="application/octet-stream",
                size=10,
            )

        s3.begin_multipart.assert_not_called()


class TestSendingParts:
    @pytest.mark.asyncio
    async def test_a_short_part_is_refused_as_it_arrives(self, session: AsyncSession):
        """Storage only reports this at completion, by which point every
        other part has been sent for nothing."""
        s3 = _s3()
        _, service, started = await _started(session, s3)

        with pytest.raises(PartTooSmallError):
            await service.upload_part(
                upload_id=started.upload_id,
                user_id=(await _owner(session, started.upload_id)),
                part_number=1,
                body=b"x" * (MIN_PART_BYTES - 1),
            )

        s3.upload_part.assert_not_called()

    @pytest.mark.asyncio
    async def test_the_last_part_may_be_short(self, session: AsyncSession):
        s3 = _s3()
        user, service, started = await _started(session, s3)

        await service.upload_part(
            upload_id=started.upload_id,
            user_id=user.id,
            part_number=3,
            body=b"x" * 100,
        )

        s3.upload_part.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_somebody_elses_upload_is_not_found(self, session: AsyncSession):
        """Not "forbidden": that would confirm the id exists."""
        _, service, started = await _started(session, _s3())
        stranger = await make_user(session)

        with pytest.raises(UploadNotFoundError):
            await service.upload_part(
                upload_id=started.upload_id,
                user_id=stranger.id,
                part_number=1,
                body=b"x" * PART_SIZE,
            )


class TestResuming:
    @pytest.mark.asyncio
    async def test_what_arrived_is_read_from_storage(self, session: AsyncSession):
        """Not from a counter in the session row: storage decides whether
        a part exists, and a row that disagreed would resume into a
        corrupt file."""
        s3 = _s3(parts=[_part(1), _part(2)])
        user, service, started = await _started(session, s3)

        status = await service.status(upload_id=started.upload_id, user_id=user.id)

        assert status.received_parts == [1, 2]
        assert status.received_bytes == 2 * PART_SIZE
        s3.list_parts.assert_awaited()


class TestCompleting:
    @pytest.mark.asyncio
    async def test_it_creates_the_video_and_queues_the_encode(
        self, session: AsyncSession
    ):
        content = b"x" * 120
        s3 = _s3(stored=content, parts=[_part(1)])
        user, service, started = await _started(session, s3, size=len(content))

        response = await service.complete(
            upload_id=started.upload_id,
            user_id=user.id,
            name="clip",
            description="",
            privacy="public",
            category="general",
            thumbnail=None,
        )

        assert response.status == "accepted"
        s3.complete_multipart.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_declared_size_is_checked_against_what_arrived(
        self, session: AsyncSession
    ):
        """Otherwise declaring one megabyte and sending two gigabytes
        would pass the limit at the only point it is enforced."""
        s3 = _s3(stored=b"x" * 10, parts=[_part(1)])
        user, service, started = await _started(session, s3, size=5_000_000)

        with pytest.raises(UploadSizeMismatchError):
            await service.complete(
                upload_id=started.upload_id,
                user_id=user.id,
                name="clip",
                description="",
                privacy="public",
                category="general",
                thumbnail=None,
            )

    @pytest.mark.asyncio
    async def test_a_failure_takes_the_stored_object_with_it(
        self, session: AsyncSession
    ):
        """Nothing references the object once the session row is gone, so
        it would be bytes no listing explains."""
        s3 = _s3(stored=b"x" * 10, parts=[_part(1)])
        user, service, started = await _started(session, s3, size=5_000_000)

        with pytest.raises(UploadSizeMismatchError):
            await service.complete(
                upload_id=started.upload_id,
                user_id=user.id,
                name="clip",
                description="",
                privacy="public",
                category="general",
                thumbnail=None,
            )

        # Every version: the bucket is versioned, so an ordinary delete
        # would leave the file behind as a noncurrent version and a
        # refused upload is an ordinary thing.
        s3.delete_all_versions.assert_awaited_once()
        assert await _session_row(session, started.upload_id) is None

    @pytest.mark.asyncio
    async def test_completing_with_nothing_sent_is_refused(self, session: AsyncSession):
        s3 = _s3(parts=[])
        user, service, started = await _started(session, s3)

        with pytest.raises(UploadSizeMismatchError):
            await service.complete(
                upload_id=started.upload_id,
                user_id=user.id,
                name="clip",
                description="",
                privacy="public",
                category="general",
                thumbnail=None,
            )

    @pytest.mark.asyncio
    async def test_the_session_does_not_outlive_the_upload(self, session: AsyncSession):
        content = b"x" * 120
        s3 = _s3(stored=content, parts=[_part(1)])
        user, service, started = await _started(session, s3, size=len(content))

        await service.complete(
            upload_id=started.upload_id,
            user_id=user.id,
            name="clip",
            description="",
            privacy="public",
            category="general",
            thumbnail=None,
        )

        assert await _session_row(session, started.upload_id) is None


class TestGivingUp:
    @pytest.mark.asyncio
    async def test_aborting_releases_the_parts(self, session: AsyncSession):
        s3 = _s3()
        user, service, started = await _started(session, s3)

        await service.abort(upload_id=started.upload_id, user_id=user.id)

        s3.abort_multipart.assert_awaited_once()
        assert await _session_row(session, started.upload_id) is None

    @pytest.mark.asyncio
    async def test_abandoned_uploads_are_swept(self, session: AsyncSession):
        """An unfinished multipart upload holds every part already sent
        and appears in no object listing, so the space is spent and
        invisible until something aborts it."""
        s3 = _s3()
        _, service, started = await _started(session, s3)

        # Through Core, with the value spelled out: the column carries
        # onupdate=now(), so an ORM flush would helpfully undo exactly the
        # thing this test is setting up.
        await session.execute(
            update(UploadSession)
            .where(UploadSession.id == started.upload_id)
            .values(updated_at=datetime.now(timezone.utc) - timedelta(days=2))
        )
        await session.flush()

        swept = await service.sweep_abandoned()

        assert swept == 1
        s3.abort_multipart.assert_awaited_once()
        assert await _session_row(session, started.upload_id) is None

    @pytest.mark.asyncio
    async def test_an_upload_in_progress_is_left_alone(self, session: AsyncSession):
        s3 = _s3()
        _, service, started = await _started(session, s3)

        assert await service.sweep_abandoned() == 0
        s3.abort_multipart.assert_not_called()


async def _session_row(session: AsyncSession, upload_id):
    return await session.scalar(
        select(UploadSession).where(UploadSession.id == upload_id)
    )


async def _owner(session: AsyncSession, upload_id):
    row = await _session_row(session, upload_id)
    return row.user_id
