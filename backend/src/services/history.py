from typing import List, Tuple
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.pagination import paginate_query
from src.errors.history import HistoryEntryNotFoundError
from src.models import Video, WatchHistory
from src.schemas.history import HistoryVideoItem


class HistoryService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, user_id: UUID, page: int, size: int) -> Tuple[List[HistoryVideoItem], int]:
        return await paginate_query(
            self.session,
            WatchHistory,
            page=page,
            size=size,
            filters=[WatchHistory.user_id == user_id],
            order_by=WatchHistory.last_watched_at.desc(),
            preload=[
                selectinload(WatchHistory.video).selectinload(Video.channel),
                selectinload(WatchHistory.video).selectinload(Video.privacy),
            ],
            mapper=self._to_item,
        )

    async def remove(self, user_id: UUID, video_id: UUID) -> None:
        entry = await self.session.scalar(
            select(WatchHistory).where(
                WatchHistory.user_id == user_id,
                WatchHistory.video_id == video_id,
            )
        )
        if not entry:
            raise HistoryEntryNotFoundError()
        await self.session.delete(entry)
        await self.session.commit()

    async def clear(self, user_id: UUID) -> None:
        await self.session.execute(
            delete(WatchHistory).where(WatchHistory.user_id == user_id)
        )
        await self.session.commit()

    @staticmethod
    def _to_item(entry: WatchHistory) -> HistoryVideoItem:
        v = entry.video
        return HistoryVideoItem(
            id=v.id,
            title=v.name,
            thumbnail=v.thumbnail_path or "",
            channel_name=v.channel.name if v.channel else "",
            channel_avatar=v.channel.avatar_path or "" if v.channel else "",
            views_count=v.views_count,
            created_at=v.created_at,
            last_watched_at=entry.last_watched_at,
        )
