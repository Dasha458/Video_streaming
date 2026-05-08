from typing import List, Tuple
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors.notifications import NotificationNotFoundError
from src.models import Notification
from src.schemas.notification import NotificationResponse, NotificationsPage


class NotificationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, user_id: UUID, page: int, size: int) -> NotificationsPage:
        total = await self.session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id)
        ) or 0

        unread_count = await self.session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
        ) or 0

        result = await self.session.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        notifications = result.scalars().all()
        items = [NotificationResponse.model_validate(n) for n in notifications]
        return NotificationsPage(items=items, unread_count=unread_count, total=total)

    async def mark_read(self, user_id: UUID, notification_id: UUID) -> None:
        notification = await self.session.scalar(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        if not notification:
            raise NotificationNotFoundError()
        notification.is_read = True
        await self.session.commit()

    async def mark_all_read(self, user_id: UUID) -> None:
        await self.session.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
            .values(is_read=True)
        )
        await self.session.commit()

    @classmethod
    async def create_notification(
        cls,
        session: AsyncSession,
        user_id: UUID,
        content: str,
        link: str,
        notification_type: str | None = None,
    ) -> None:
        session.add(Notification(
            user_id=user_id,
            content=content,
            link=link,
            notification_type=notification_type,
        ))
        await session.commit()
