"""
Real-Postgres tests for the one-file-one-video rule.

A file exists on the platform once: `Video.hash` is unique across the
whole table, and that is the product rule, not an accident of the schema.
What was wrong was everything around it.

Every rejection raised the same error, phrased as "video with the same
hash already exists" -- which told an uploader looking at their own
earlier copy exactly as little as it told a stranger.

Worse, the hash could be held by wreckage. `_insert_video` commits the
row before the file is uploaded, so a storage failure leaves a row stuck
in `queued`; a failed encode leaves one in `failed`. Neither can be
deleted by its owner in the queued case, and both keep the hash, so the
person who uploaded the file could never upload their own file again.
"""

from datetime import timedelta
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.status_ids import (
    STATUS_FAILED_ID,
    STATUS_PROCESSING_ID,
    STATUS_QUEUED_ID,
    STATUS_READY_ID,
)
from src.errors.files import AlreadyUploadedError, DuplicateVideoError
from src.models import Video
from src.services.files import FileService
from tests.integration.conftest import make_channel, make_user, make_video, now

pytestmark = pytest.mark.integration

HASH = "deadbeefdeadbeefdeadbeefdeadbeef"


def _s3():
    s3 = AsyncMock()
    s3.list_keys = AsyncMock(return_value=[])
    s3.delete_prefix = AsyncMock()
    s3.delete_file = AsyncMock()
    s3.upload_file = AsyncMock()
    return s3


def _service(session: AsyncSession, s3=None) -> FileService:
    broker = AsyncMock()
    broker.publish = AsyncMock()
    return FileService(session=session, s3_client=s3 or _s3(), broker=broker)


#: The upload is in storage by the time any of this runs, so the hash is
#: a value, not a file to read.
HASH_OF_THE_FILE = "0123456789abcdef0123456789abcdef"


async def _upload(service: FileService, user_id, video_hash: str = HASH_OF_THE_FILE):
    return await service.register_uploaded_video(
        video_id=uuid4(),
        object_key="irrelevant.mp4",
        video_hash=video_hash,
        size=25,
        name="clip",
        description="",
        privacy="public",
        category="general",
        user_id=user_id,
        thumbnail=None,
    )


async def _existing(session: AsyncSession, channel, *, status_id, created_at=None):
    """A row already holding the hash the next upload will produce."""
    video = await make_video(
        session, channel, status_id=status_id, created_at=created_at
    )
    video.hash = HASH_OF_THE_FILE
    await session.flush()
    return video


@pytest.mark.asyncio
async def test_a_strangers_copy_is_refused_without_revealing_it(
    session: AsyncSession,
):
    """The rule is enforced, and nothing about the other video leaks."""
    stranger = await make_user(session)
    stranger_channel = await make_channel(session, stranger)
    await _existing(session, stranger_channel, status_id=STATUS_READY_ID)

    uploader = await make_user(session)
    await make_channel(session, uploader)

    with pytest.raises(DuplicateVideoError) as refused:
        await _upload(_service(session), uploader.id)

    message = str(refused.value)
    assert "already on the platform" in message
    # Not the id, not the channel, not the owner, not the title.
    assert str(stranger.id) not in message
    assert stranger_channel.name not in message


@pytest.mark.asyncio
async def test_my_own_copy_says_so(session: AsyncSession):
    """A different error, because the uploader can be told whose it is."""
    user = await make_user(session)
    channel = await make_channel(session, user)
    await _existing(session, channel, status_id=STATUS_READY_ID)

    with pytest.raises(AlreadyUploadedError) as refused:
        await _upload(_service(session), user.id)

    assert "already uploaded" in str(refused.value).lower()


@pytest.mark.asyncio
async def test_a_failed_encode_does_not_block_re_uploading_my_own_file(
    session: AsyncSession,
):
    """The case that made the file permanently un-uploadable.

    The encode failed, so the row is finished and will not change. Its
    hash was still held, and the error told the owner the file "already
    exists" -- the file they were trying to replace.
    """
    user = await make_user(session)
    channel = await make_channel(session, user)
    dead = await _existing(session, channel, status_id=STATUS_FAILED_ID)

    response = await _upload(_service(session), user.id)

    assert response.status == "accepted"
    gone = await session.scalar(select(Video.id).where(Video.id == dead.id))
    assert gone is None, "the failed row should have been reclaimed"


@pytest.mark.asyncio
async def test_a_row_stuck_in_queued_is_reclaimed_once_it_is_clearly_stuck(
    session: AsyncSession,
):
    """`_insert_video` commits before the upload, so a storage failure
    leaves exactly this: queued for ever, undeletable, holding the hash."""
    user = await make_user(session)
    channel = await make_channel(session, user)
    stuck = await _existing(
        session,
        channel,
        status_id=STATUS_QUEUED_ID,
        created_at=now() - timedelta(hours=2),
    )

    response = await _upload(_service(session), user.id)

    assert response.status == "accepted"
    assert await session.scalar(select(Video.id).where(Video.id == stuck.id)) is None


@pytest.mark.asyncio
async def test_a_queue_entry_from_a_moment_ago_is_left_alone(
    session: AsyncSession,
):
    """Otherwise uploading the same file twice by accident would delete
    the first attempt out from under the encoder."""
    user = await make_user(session)
    channel = await make_channel(session, user)
    fresh = await _existing(session, channel, status_id=STATUS_QUEUED_ID)

    with pytest.raises(AlreadyUploadedError):
        await _upload(_service(session), user.id)

    assert await session.scalar(select(Video.id).where(Video.id == fresh.id)) is not None


@pytest.mark.asyncio
async def test_a_video_being_encoded_is_never_reclaimed(session: AsyncSession):
    """The encoder is writing into that prefix right now."""
    user = await make_user(session)
    channel = await make_channel(session, user)
    busy = await _existing(session, channel, status_id=STATUS_PROCESSING_ID)

    with pytest.raises(AlreadyUploadedError):
        await _upload(_service(session), user.id)

    assert await session.scalar(select(Video.id).where(Video.id == busy.id)) is not None


@pytest.mark.asyncio
async def test_reclaiming_clears_what_the_dead_row_left_in_storage(
    session: AsyncSession,
):
    """A reclaimed row's bytes would otherwise be orphaned for good: once
    the row is gone, nothing knows the prefix existed."""
    user = await make_user(session)
    channel = await make_channel(session, user)
    dead = await _existing(session, channel, status_id=STATUS_FAILED_ID)

    s3 = _s3()
    await _upload(_service(session, s3), user.id)

    prefixes = [call.args[0] for call in s3.delete_prefix.await_args_list]
    assert f"{dead.id}/" in prefixes


@pytest.mark.asyncio
async def test_two_different_files_from_the_same_person_are_both_accepted(
    session: AsyncSession,
):
    """The guard rejects a repeated file, not a repeated uploader."""
    user = await make_user(session)
    await make_channel(session, user)
    service = _service(session)

    first = await _upload(service, user.id)
    second = await _upload(service, user.id, video_hash="ffffffffffffffffffffffffffffffff")

    assert first.status == "accepted"
    assert second.status == "accepted"
    assert first.files[0].file_id != second.files[0].file_id
