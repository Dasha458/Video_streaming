"""
Who is allowed to see a video.

One rule, one place. It is applied when the watch page asks for a video,
when the client asks for a stream URL, and again for every media object
the player fetches -- three entry points that must not be able to drift
apart, because the weakest of them is the one that decides.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.status_ids import PRIVACY_PUBLIC_ID, STATUS_READY_ID
from src.models import Video


def is_visible_to(video: Video, user_id: UUID | None) -> bool:
    """A video is visible when it is public and finished encoding.

    Its owner also sees it while it is private or still processing; nobody
    else does, not even signed in.
    """
    if video.privacy_id == PRIVACY_PUBLIC_ID and video.status_id == STATUS_READY_ID:
        return True
    if user_id is None:
        return False
    owner_id = video.channel.user_id if video.channel else None
    return owner_id == user_id


async def load_visible_video(
    session: AsyncSession, video_id: UUID, user_id: UUID | None
) -> Video | None:
    """The video, or ``None`` when the caller may not see it.

    Callers answer "not found" rather than "forbidden" so the response
    does not confirm that a private video exists.
    """
    video = await session.scalar(
        select(Video).options(selectinload(Video.channel)).where(Video.id == video_id)
    )
    if video is None or not is_visible_to(video, user_id):
        return None
    return video
