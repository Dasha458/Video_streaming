"""
Real-Postgres tests for who may obtain a video's media.

The rule is enforced in three places -- the watch page, the stream URL and
every media object the player fetches -- and they all read the same
database rows, so this is where their agreement can actually be checked.
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.status_ids import PRIVACY_PRIVATE_ID, STATUS_PROCESSING_ID
from src.errors.files import MediaAccessDeniedError
from src.errors.videos import VideoNotFoundError
from src.services.streaming import StreamService
from tests.integration.conftest import make_channel, make_user, make_video

pytestmark = pytest.mark.integration


def _signer():
    signer = AsyncMock()
    signer.expires_in = 3600
    signer.create_signed_url = AsyncMock(
        return_value={
            "path": "videos/x/master.m3u8",
            "signed_url": "http://minio:9000/signed",
            "expires_in": 3600,
        }
    )
    return signer


async def _with_media(session: AsyncSession, channel, **kw):
    video = await make_video(session, channel, **kw)
    video.video_path = f"minio/videos/{video.id}/master.m3u8"
    await session.flush()
    return video


@pytest.mark.asyncio
async def test_public_video_yields_a_url_to_anyone(session: AsyncSession):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await _with_media(session, channel)

    url, expires_in = await StreamService(session, _signer()).stream_url(
        video.id, user_id=None
    )
    assert url == f"/minio/videos/{video.id}/master.m3u8"
    assert expires_in == 3600


@pytest.mark.asyncio
async def test_private_video_yields_a_url_only_to_its_owner(session: AsyncSession):
    owner = await make_user(session)
    stranger = await make_user(session)
    channel = await make_channel(session, owner)
    video = await _with_media(session, channel, privacy_id=PRIVACY_PRIVATE_ID)

    service = StreamService(session, _signer())

    with pytest.raises(VideoNotFoundError):
        await service.stream_url(video.id, user_id=None)
    with pytest.raises(VideoNotFoundError):
        await service.stream_url(video.id, user_id=stranger.id)

    url, _ = await service.stream_url(video.id, user_id=owner.id)
    assert url.endswith("master.m3u8")


@pytest.mark.asyncio
async def test_a_segment_of_a_private_video_is_not_signed(session: AsyncSession):
    """The gateway asks per object; refusing the playlist is not enough."""
    owner = await make_user(session)
    stranger = await make_user(session)
    channel = await make_channel(session, owner)
    video = await _with_media(session, channel, privacy_id=PRIVACY_PRIVATE_ID)

    signer = _signer()
    service = StreamService(session, signer)
    segment = f"/minio/videos/{video.id}/720p/seg00042.ts"

    with pytest.raises(MediaAccessDeniedError):
        await service.authorize_media(segment, user_id=None)
    with pytest.raises(MediaAccessDeniedError):
        await service.authorize_media(segment, user_id=stranger.id)
    signer.create_signed_url.assert_not_awaited()

    await service.authorize_media(segment, user_id=owner.id)
    signer.create_signed_url.assert_awaited_once_with(segment)


@pytest.mark.asyncio
async def test_a_video_still_encoding_is_not_streamable_by_others(
    session: AsyncSession,
):
    owner = await make_user(session)
    stranger = await make_user(session)
    channel = await make_channel(session, owner)
    video = await _with_media(session, channel, status_id=STATUS_PROCESSING_ID)

    service = StreamService(session, _signer())
    with pytest.raises(VideoNotFoundError):
        await service.stream_url(video.id, user_id=stranger.id)


@pytest.mark.asyncio
async def test_a_path_naming_a_video_that_does_not_exist_is_refused(
    session: AsyncSession,
):
    signer = _signer()
    service = StreamService(session, signer)

    with pytest.raises(MediaAccessDeniedError):
        await service.authorize_media(
            f"/minio/videos/{uuid.uuid4()}/master.m3u8", user_id=None
        )
    signer.create_signed_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_paths_outside_a_video_folder_are_refused(session: AsyncSession):
    """The old endpoint would have signed any of these."""
    signer = _signer()
    service = StreamService(session, signer)

    for path in (
        "/minio/videos/../../etc/passwd",
        "/minio/private-bucket/backups/dump.sql",
        "/minio/videos/master.m3u8",
        "/minio/video-thumbnails/nested/../secret.jpg",
    ):
        with pytest.raises(MediaAccessDeniedError):
            await service.authorize_media(path, user_id=None)

    signer.create_signed_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_thumbnail_follows_its_video(session: AsyncSession):
    """Thumbnails live in their own bucket under an unrelated filename.

    They are still a video's object, so the same rule decides: a private
    video's thumbnail is not signed for anyone but its owner.
    """
    owner = await make_user(session)
    stranger = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel, privacy_id=PRIVACY_PRIVATE_ID)
    thumb = f"/minio/video-thumbnails/{uuid.uuid4()}.jpg"
    video.thumbnail_path = thumb
    await session.flush()

    signer = _signer()
    service = StreamService(session, signer)

    with pytest.raises(MediaAccessDeniedError):
        await service.authorize_media(thumb, user_id=stranger.id)
    signer.create_signed_url.assert_not_awaited()

    await service.authorize_media(thumb, user_id=owner.id)
    signer.create_signed_url.assert_awaited_once_with(thumb)


@pytest.mark.asyncio
async def test_a_public_video_thumbnail_is_signed_for_anyone(session: AsyncSession):
    owner = await make_user(session)
    channel = await make_channel(session, owner)
    video = await make_video(session, channel)
    thumb = f"/minio/video-thumbnails/{uuid.uuid4()}.jpg"
    video.thumbnail_path = thumb
    await session.flush()

    signer = _signer()
    await StreamService(session, signer).authorize_media(thumb, user_id=None)
    signer.create_signed_url.assert_awaited_once_with(thumb)


@pytest.mark.asyncio
async def test_a_thumbnail_belonging_to_no_video_is_refused(session: AsyncSession):
    signer = _signer()
    service = StreamService(session, signer)

    with pytest.raises(MediaAccessDeniedError):
        await service.authorize_media(
            f"/minio/video-thumbnails/{uuid.uuid4()}.jpg", user_id=None
        )
    signer.create_signed_url.assert_not_awaited()
