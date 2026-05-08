from typing import List, Tuple
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from src.errors.watch_later import AlreadyInWatchLaterError, WatchLaterEntryNotFoundError
from src.models import Video, WatchLater
from src.schemas.watch_later import WatchLaterVideoItem


class WatchLaterService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, user_id: UUID, page: int, size: int) -> Tuple[List[WatchLaterVideoItem], int]:
        total = await self.session.scalar(
            select(func.count())
            .select_from(WatchLater)
            .where(WatchLater.user_id == user_id)
        ) or 0

        result = await self.session.execute(
            select(WatchLater)
            .where(WatchLater.user_id == user_id)
            .options(
                selectinload(WatchLater.video).selectinload(Video.channel),
            )
            .order_by(WatchLater.added_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        entries = result.scalars().all()
        return [self._to_item(e) for e in entries], total

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
