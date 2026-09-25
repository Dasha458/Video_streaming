from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.pagination import paginate_query
from src.errors.notifications import NotificationNotFoundError
from src.models import Notification
from src.schemas.notification import NotificationResponse, NotificationsPage


class NotificationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, user_id: UUID, page: int, size: int) -> NotificationsPage:
        items, total = await paginate_query(
            self.session,
            Notification,
            page=page,
            size=size,
            filters=[Notification.user_id == user_id],
            order_by=Notification.created_at.desc(),
            mapper=NotificationResponse.model_validate,
        )

        unread_count = (
            await self.session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.user_id == user_id,
                    Notification.is_read.is_(False),
                )
            )
            or 0
        )

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
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
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
        session.add(
            Notification(
                user_id=user_id,
                content=content,
                link=link,
                notification_type=notification_type,
            )
        )
        await session.commit()
