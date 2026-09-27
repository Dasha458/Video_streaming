"""
Real-Postgres tests for VideoService's visibility rules and view recording.

Both behaviours are defined by the database -- a partial unique index that
only applies to signed-in viewers, and ON CONFLICT deciding whether a view
is new -- so a mocked session proves nothing about either.
"""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.status_ids import PRIVACY_PRIVATE_ID, STATUS_PROCESSING_ID
from src.errors.videos import VideoNotFoundError
from src.models import Video, VideoView
from src.services.videos import VideoService
from tests.integration.conftest import make_channel, make_user, make_video

pytestmark = pytest.mark.integration


async def _views(session: AsyncSession, video_id) -> int:
    return int(
        await session.scalar(
            select(func.count(VideoView.id)).where(VideoView.video_id == video_id)
        )
        or 0
    )


async def _views_count(session: AsyncSession, video_id) -> int:
    """The denormalised counter, which must agree with the rows."""
    return int(
        await session.scalar(select(Video.views_count).where(Video.id == video_id)) or 0
    )


@pytest.mark.asyncio
async def test_private_video_is_hidden_from_everyone_but_its_owner(
    session: AsyncSession,
):
    owner = await make_user(session)
    stranger = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel, privacy_id=PRIVACY_PRIVATE_ID)

    service = VideoService(session)

    # Anonymous: used to receive 200 and the full metadata.
    with pytest.raises(VideoNotFoundError):
        await service.get_playback(video.id, user_id=None)

    # A signed-in stranger is no better placed than an anonymous one.
    with pytest.raises(VideoNotFoundError):
        await service.get_playback(video.id, user_id=stranger.id)

    # The owner still sees their own video.
    playback = await service.get_playback(video.id, user_id=owner.id)
    assert playback.id == video.id


@pytest.mark.asyncio
async def test_a_video_still_encoding_is_not_playable_by_others(
    session: AsyncSession,
):
    owner = await make_user(session)
    stranger = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel, status_id=STATUS_PROCESSING_ID)

    service = VideoService(session)
    with pytest.raises(VideoNotFoundError):
        await service.get_playback(video.id, user_id=stranger.id)
    assert (await service.get_playback(video.id, user_id=owner.id)).id == video.id


@pytest.mark.asyncio
async def test_the_same_signed_out_viewer_is_counted_once(session: AsyncSession):
    """A view is one viewer, not one page load.

    Signed-out visits used to be dropped before they reached the database
    at all; counting them raw would have made "views" mean neither unique
    viewers nor hits.
    """
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    service = VideoService(session)
    for _ in range(3):
        await service.get_playback(
            video.id, user_id=None, source_type="search", viewer_key="anon:same"
        )

    assert await _views(session, video.id) == 1
    assert await _views_count(session, video.id) == 1


@pytest.mark.asyncio
async def test_different_signed_out_viewers_are_counted_separately(
    session: AsyncSession,
):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    service = VideoService(session)
    await service.get_playback(video.id, user_id=None, viewer_key="anon:one")
    await service.get_playback(video.id, user_id=None, viewer_key="anon:two")
    await service.get_playback(video.id, user_id=None, viewer_key="fp:abc123")

    assert await _views(session, video.id) == 3
    assert await _views_count(session, video.id) == 3


@pytest.mark.asyncio
async def test_a_visit_with_no_viewer_records_nothing(session: AsyncSession):
    """Without an identity there is no viewer to count, so we do not guess."""
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    await VideoService(session).get_playback(video.id, user_id=None)

    assert await _views(session, video.id) == 0


@pytest.mark.asyncio
async def test_a_signed_in_viewer_is_counted_once(session: AsyncSession):
    owner = await make_user(session)
    viewer = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    service = VideoService(session)
    key = f"user:{viewer.id}"
    await service.get_playback(video.id, user_id=viewer.id, viewer_key=key)
    await service.get_playback(video.id, user_id=viewer.id, viewer_key=key)

    assert await _views(session, video.id) == 1
    assert await _views_count(session, video.id) == 1


@pytest.mark.asyncio
async def test_traffic_source_is_filled_in_on_a_later_visit(session: AsyncSession):
    """It used to be written on the first view only and never again."""
    owner = await make_user(session)
    viewer = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)

    service = VideoService(session)
    key = f"user:{viewer.id}"
    await service.get_playback(video.id, user_id=viewer.id, viewer_key=key)
    stored = await session.scalar(
        select(VideoView.source_type).where(
            VideoView.video_id == video.id, VideoView.viewer_key == key
        )
    )
    assert stored == "unknown"

    await service.get_playback(
        video.id, user_id=viewer.id, source_type="playlist", viewer_key=key
    )
    stored = await session.scalar(
        select(VideoView.source_type).where(
            VideoView.video_id == video.id, VideoView.viewer_key == key
        )
    )
    assert stored == "playlist"


@pytest.mark.asyncio
async def test_search_visibility_filter_keeps_only_public_ready_videos(
    session: AsyncSession,
):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    public = await make_video(session, channel)
    private = await make_video(session, channel, privacy_id=PRIVACY_PRIVATE_ID)
    encoding = await make_video(session, channel, status_id=STATUS_PROCESSING_ID)
    missing = uuid.uuid4()

    visible = await VideoService(session).filter_public_ready_ids(
        [public.id, private.id, encoding.id, missing]
    )
    assert visible == {public.id}
