"""
Handing out access to a video's media.

This replaces ``GET /api/files/sign_url``, which took a path and signed
it. It asked nothing about who was calling or what the path belonged to,
and it sat behind the public ``/api/`` prefix, so anyone who knew or
guessed an object key could have the server sign it for them.

Access is now decided per video: the caller names a video, the privacy
rule in :mod:`src.services.video_access` decides, and only then is a URL
produced. The same rule is applied again to every media object the player
fetches, because an object key under ``videos/<video_id>/`` says which
video it belongs to.
"""

import logging
import re
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.errors.files import MediaAccessDeniedError
from src.errors.videos import VideoNotFoundError
from src.models import Video
from src.services.video_access import is_visible_to, load_visible_video

if TYPE_CHECKING:
    from src.services.file_signing import FileSigningService

# Playlists and segments live in the "videos" bucket under a folder named
# after the video. That id in the key is what lets a segment request be
# authorised on its own, without inventing a token to carry the decision.
_MEDIA_KEY = re.compile(r"^/minio/videos/(?P<video_id>[^/]+)/.+$")

# Thumbnails sit in their own bucket under an unrelated filename, so the
# video they belong to has to be found by the stored path.
_THUMBNAIL_KEY = re.compile(r"^/minio/video-thumbnails/[^/]+$")


class StreamService:
    def __init__(self, session: AsyncSession, signer: "FileSigningService") -> None:
        self.session = session
        self.signer = signer

    async def stream_url(self, video_id: UUID, user_id: UUID | None) -> tuple[str, int]:
        """The playable URL for a video the caller is allowed to watch.

        Returns the gateway path rather than a presigned object URL on
        purpose: an HLS master playlist names its variants and segments
        relatively, so they have to resolve back through the gateway to be
        authorised individually. Handing out a presigned URL for the
        playlist alone would give the player a document whose every
        reference 404s.
        """
        video = await load_visible_video(self.session, video_id, user_id)
        if video is None or not video.video_path:
            raise VideoNotFoundError()

        path = video.video_path.lstrip("/")
        return f"/{path}", self.signer.expires_in

    async def authorize_media(self, file_path: str, user_id: UUID | None) -> dict:
        """Sign one media object, if the caller may watch the video it belongs to.

        The gateway calls this for every playlist and segment request. A
        path that does not belong to a video, or belongs to one the caller
        cannot see, is refused rather than signed.
        """
        path = file_path.split("?", 1)[0]

        media = _MEDIA_KEY.match(path)
        if media:
            try:
                video_id = UUID(media.group("video_id"))
            except ValueError as exc:
                raise MediaAccessDeniedError() from exc
            video = await load_visible_video(self.session, video_id, user_id)
        elif _THUMBNAIL_KEY.match(path):
            video = await self._video_by_thumbnail(path, user_id)
        else:
            # Anything that is not a video's own object. The endpoint this
            # replaced would have signed it.
            raise MediaAccessDeniedError()

        if video is None:
            logging.info(
                "Refused to sign %s for %s", path, user_id or "an anonymous caller"
            )
            raise MediaAccessDeniedError()

        return await self.signer.create_signed_url(file_path)

    async def _video_by_thumbnail(
        self, path: str, user_id: UUID | None
    ) -> Video | None:
        video = await self.session.scalar(
            select(Video)
            .options(selectinload(Video.channel))
            .where(Video.thumbnail_path == path)
        )
        if video is None or not is_visible_to(video, user_id):
            return None
        return video
