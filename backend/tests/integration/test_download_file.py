"""
Real-Postgres tests for what the Download button hands over.

It could not hand over a playable file by any route, which is why
neither route was ever reported broken. Asked for a resolution the
service returned the .m3u8 playlist with a .mp4 filename -- a few
hundred bytes of text saved as a video. Asked for the original it looked
up the key ``str(video.id)``, while the upload is stored as
``<id><suffix>`` and the converter deletes it the moment the encode
succeeds.

There is one downloadable file per video now, built at encode time, and
these say so: the right key, a safe filename, the owner only, and an
explanation rather than "not found" when it is not there.
"""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.status_ids import STATUS_FAILED_ID, STATUS_PROCESSING_ID, STATUS_READY_ID
from src.errors.files import DownloadNotReadyError, DownloadUnavailableError
from src.errors.videos import VideoNotFoundError
from src.services.files import FileService
from tests.integration.conftest import make_channel, make_user, make_video

pytestmark = pytest.mark.integration


def _s3(present: bool = True):
    s3 = AsyncMock()
    s3.list_keys = AsyncMock(
        side_effect=lambda prefix, bucket_name=None: [prefix] if present else []
    )
    return s3


def _service(session: AsyncSession, present: bool = True) -> FileService:
    return FileService(session=session, s3_client=_s3(present), broker=AsyncMock())


@pytest.mark.asyncio
async def test_it_returns_the_file_the_converter_built(session: AsyncSession):
    user = await make_user(session)
    channel = await make_channel(session, user)
    video = await make_video(session, channel, name="My Clip")

    key, filename, media_type = await _service(session).get_video_file(
        video.id, user.id
    )

    assert key == f"{video.id}/download.mp4"
    assert filename == "My Clip.mp4"
    assert media_type == "video/mp4"


@pytest.mark.asyncio
async def test_the_filename_cannot_break_the_header_or_the_filesystem(
    session: AsyncSession,
):
    """The name goes into Content-Disposition between quotes, and then
    into a filename on the viewer's machine."""
    user = await make_user(session)
    channel = await make_channel(session, user)
    video = await make_video(session, channel, name='a/b:c*d?e"f<g>h|i')

    _, filename, _ = await _service(session).get_video_file(video.id, user.id)

    assert filename == "a_b_c_d_e_f_g_h_i.mp4"
    assert '"' not in filename


@pytest.mark.asyncio
async def test_a_title_made_only_of_refused_characters_still_downloads(
    session: AsyncSession,
):
    user = await make_user(session)
    channel = await make_channel(session, user)
    video = await make_video(session, channel, name="///")

    _, filename, _ = await _service(session).get_video_file(video.id, user.id)

    assert filename == "video.mp4"


@pytest.mark.asyncio
async def test_somebody_elses_video_is_not_downloadable(session: AsyncSession):
    """Download is the owner's, and the button is hidden for everyone
    else -- it used to be shown to all and refused by the server."""
    owner = await make_user(session)
    video = await make_video(session, await make_channel(session, owner))
    stranger = await make_user(session)

    with pytest.raises(VideoNotFoundError):
        await _service(session).get_video_file(video.id, stranger.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_id", [STATUS_PROCESSING_ID, STATUS_FAILED_ID])
async def test_a_video_that_is_not_ready_says_so(session: AsyncSession, status_id):
    """"Not found", for a video the owner is looking at in Studio,
    explains nothing."""
    user = await make_user(session)
    channel = await make_channel(session, user)
    video = await make_video(session, channel, status_id=status_id)

    with pytest.raises(DownloadNotReadyError):
        await _service(session).get_video_file(video.id, user.id)


@pytest.mark.asyncio
async def test_a_video_encoded_before_this_existed_is_named_as_such(
    session: AsyncSession,
):
    """Everything uploaded before the converter started building the file
    lands here until the backfill runs."""
    user = await make_user(session)
    channel = await make_channel(session, user)
    video = await make_video(session, channel, status_id=STATUS_READY_ID)

    with pytest.raises(DownloadUnavailableError):
        await _service(session, present=False).get_video_file(video.id, user.id)
