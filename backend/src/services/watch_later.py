from typing import List, Tuple
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.pagination import paginate_query
from src.errors.watch_later import AlreadyInWatchLaterError, WatchLaterEntryNotFoundError
from src.models import Video, WatchLater
from src.schemas.watch_later import WatchLaterVideoItem


class WatchLaterService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, user_id: UUID, page: int, size: int) -> Tuple[List[WatchLaterVideoItem], int]:
        return await paginate_query(
            self.session,
            WatchLater,
            page=page,
            size=size,
            filters=[WatchLater.user_id == user_id],
            order_by=WatchLater.added_at.desc(),
            preload=[selectinload(WatchLater.video).selectinload(Video.channel)],
            mapper=self._to_item,
        )

    async def add(self, user_id: UUID, video_id: UUID) -> None:
        entry = WatchLater(user_id=user_id, video_id=video_id)
        self.session.add(entry)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise AlreadyInWatchLaterError()

    async def remove(self, user_id: UUID, video_id: UUID) -> None:
        entry = await self.session.scalar(
            select(WatchLater).where(
                WatchLater.user_id == user_id,
                WatchLater.video_id == video_id,
            )
        )
        if not entry:
            raise WatchLaterEntryNotFoundError()
        await self.session.delete(entry)
        await self.session.commit()

    async def clear(self, user_id: UUID) -> None:
        await self.session.execute(
            delete(WatchLater).where(WatchLater.user_id == user_id)
        )
        await self.session.commit()

    @staticmethod
    def _to_item(entry: WatchLater) -> WatchLaterVideoItem:
        v = entry.video
        return WatchLaterVideoItem(
            id=v.id,
            title=v.name,
            thumbnail=v.thumbnail_path or "",
            channel_name=v.channel.name if v.channel else "",
            channel_avatar=v.channel.avatar_path or "" if v.channel else "",
            views_count=v.views_count,
            created_at=v.created_at,
            added_at=entry.added_at,
        )
