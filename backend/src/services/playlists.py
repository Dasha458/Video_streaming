from typing import List, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.errors.playlists import (
    PlaylistAccessForbiddenError,
    PlaylistNotFoundError,
    VideoAlreadyInPlaylistError,
    VideoNotInPlaylistError,
)
from src.models import Playlist, Video
from src.schemas.playlist import PlaylistDetailResponse, PlaylistResponse
from src.schemas.video import to_video_preview


class PlaylistService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_user_playlists(
        self, user_id: UUID
    ) -> Tuple[List[PlaylistResponse], int]:
        result = await self.session.execute(
            select(Playlist)
            .where(Playlist.user_id == user_id)
            .options(selectinload(Playlist.videos))
            .order_by(Playlist.created_at.desc())
        )
        playlists = result.scalars().all()
        items = [self._to_response(p) for p in playlists]
        return items, len(items)

    async def create(
        self, user_id: UUID, name: str, description: str | None = None
    ) -> PlaylistResponse:
        playlist = Playlist(user_id=user_id, name=name, description=description)
        self.session.add(playlist)
        await self.session.commit()
        await self.session.refresh(playlist)
        playlist.videos = []
        return self._to_response(playlist)

    async def delete(self, user_id: UUID, playlist_id: UUID) -> None:
        playlist = await self._get_owned(user_id, playlist_id)
        await self.session.delete(playlist)
        await self.session.commit()

    async def get_detail(
        self, user_id: UUID, playlist_id: UUID
    ) -> PlaylistDetailResponse:
        playlist = await self._get_owned(user_id, playlist_id)
        previews = [to_video_preview(v) for v in playlist.videos]
        return PlaylistDetailResponse(
            id=playlist.id,
            name=playlist.name,
            description=playlist.description,
            created_at=playlist.created_at,
            items=previews,
            total=len(previews),
        )

    async def add_video(self, user_id: UUID, playlist_id: UUID, video_id: UUID) -> None:
        playlist = await self._get_owned(user_id, playlist_id)
        existing_ids = {v.id for v in playlist.videos}
        if video_id in existing_ids:
            raise VideoAlreadyInPlaylistError()

        video = await self.session.scalar(select(Video).where(Video.id == video_id))
        if not video:
            from src.errors.videos import VideoNotFoundError

            raise VideoNotFoundError()

        playlist.videos.append(video)
        await self.session.commit()

    async def remove_video(
        self, user_id: UUID, playlist_id: UUID, video_id: UUID
    ) -> None:
        playlist = await self._get_owned(user_id, playlist_id)
        video = next((v for v in playlist.videos if v.id == video_id), None)
        if not video:
            raise VideoNotInPlaylistError()
        playlist.videos.remove(video)
        await self.session.commit()

    async def _get_owned(self, user_id: UUID, playlist_id: UUID) -> Playlist:
        playlist = await self.session.scalar(
            select(Playlist)
            .where(Playlist.id == playlist_id)
            .options(
                selectinload(Playlist.videos).selectinload(Video.channel),
                selectinload(Playlist.videos).selectinload(Video.privacy),
                selectinload(Playlist.videos).selectinload(Video.resolutions),
            )
        )
        if not playlist:
            raise PlaylistNotFoundError()
        if playlist.user_id != user_id:
            raise PlaylistAccessForbiddenError()
        return playlist

    @staticmethod
    def _to_response(playlist: Playlist) -> PlaylistResponse:
        return PlaylistResponse(
            id=playlist.id,
            name=playlist.name,
            description=playlist.description,
            created_at=playlist.created_at,
            video_count=len(playlist.videos),
        )
