"""
Real-Postgres tests for deleting a video.

Deleting used to leave every byte in storage: it removed the key
``str(video.id)``, while the original upload is stored as ``<id><suffix>``
and the transcoded output lives under ``<id>/``. It also refused anything
that was not ``ready``, so a video whose encode failed could be seen in
Studio and never removed.
"""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.status_ids import STATUS_FAILED_ID, STATUS_PROCESSING_ID, STATUS_QUEUED_ID
from src.errors.videos import VideoNotFoundError
from src.models import Video
from src.services.files import FileService
from tests.integration.conftest import make_channel, make_user, make_video

pytestmark = pytest.mark.integration


def _s3(keys=()):
    s3 = AsyncMock()
    s3.list_keys = AsyncMock(return_value=list(keys))
    s3.delete_prefix = AsyncMock()
    s3.delete_file = AsyncMock()
    return s3


async def _still_there(session: AsyncSession, video_id) -> bool:
    return (
        await session.scalar(select(Video.id).where(Video.id == video_id))
    ) is not None


@pytest.mark.asyncio
async def test_deleting_removes_the_transcoded_tree(session: AsyncSession):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    s3 = _s3(keys=[f"{video.id}.mp4", f"{video.id}/master.m3u8"])
    await FileService(session, s3).delete_video(video.id, owner.id)

    # The bulk of it: master playlist, per-rendition playlists, segments.
    s3.delete_prefix.assert_awaited_once_with(f"{video.id}/", bucket_name="videos")
    assert not await _still_there(session, video.id)


@pytest.mark.asyncio
async def test_deleting_removes_the_original_with_its_extension(
    session: AsyncSession,
):
    """The old code asked for the id with no suffix, which matched nothing."""
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    s3 = _s3(keys=[f"{video.id}.mp4", f"{video.id}/master.m3u8"])
    await FileService(session, s3).delete_video(video.id, owner.id)

    deleted = [c.args[0] for c in s3.delete_file.await_args_list]
    assert f"{video.id}.mp4" in deleted
    # The prefix handles everything under <id>/; it must not be deleted twice.
    assert f"{video.id}/master.m3u8" not in deleted


@pytest.mark.asyncio
async def test_deleting_removes_the_thumbnail(session: AsyncSession):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)
    video.thumbnail_path = "/minio/video-thumbnails/abc123.jpg"
    await session.flush()

    s3 = _s3()
    await FileService(session, s3).delete_video(video.id, owner.id)

    buckets = [c.kwargs.get("bucket_name") for c in s3.delete_file.await_args_list]
    assert "video-thumbnails" in buckets


@pytest.mark.asyncio
async def test_a_failed_encode_can_be_deleted(session: AsyncSession):
    """It could be seen in Studio, labelled Failed, and never removed."""
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel, status_id=STATUS_FAILED_ID)

    await FileService(session, _s3()).delete_video(video.id, owner.id)
    assert not await _still_there(session, video.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", [STATUS_QUEUED_ID, STATUS_PROCESSING_ID], ids=["queued", "processing"]
)
async def test_a_video_being_worked_on_is_held_back(session: AsyncSession, status):
    """The encoder is writing into that prefix; deleting under it would
    leave whatever it writes next with no row to belong to."""
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel, status_id=status)

    with pytest.raises(VideoNotFoundError):
        await FileService(session, _s3()).delete_video(video.id, owner.id)
    assert await _still_there(session, video.id)


@pytest.mark.asyncio
async def test_a_stranger_cannot_delete_it(session: AsyncSession):
    owner = await make_user(session)
    stranger = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    s3 = _s3()
    with pytest.raises(VideoNotFoundError):
        await FileService(session, s3).delete_video(video.id, stranger.id)

    s3.delete_prefix.assert_not_awaited()
    assert await _still_there(session, video.id)
