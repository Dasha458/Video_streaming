from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.api.dependencies.services import get_notification_service
from src.schemas.endpoint import ErrorResponse, PaginationQuery
from src.schemas.notification import NotificationsPage
from src.services.auth import get_current_user_id
from src.services.notifications import NotificationService

router_notifications = APIRouter(
    prefix="/api/notifications",
    tags=["notifications"],
    default_response_class=JSONResponse,
    responses={
        401: {"description": "Not authenticated"},
        500: {"description": "Internal server error"},
    },
)


@router_notifications.get(
    "",
    response_model=NotificationsPage,
    summary="Get notifications",
    description="Returns paginated notifications for the authenticated user.",
)
async def get_notifications(
    payload: Annotated[PaginationQuery, Depends()],
    user_id: UUID = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationsPage:
    return await service.list(user_id, payload.page, payload.size)


@router_notifications.put(
    "/{notification_id}/read",
    status_code=204,
    summary="Mark notification as read",
    description="Marks a specific notification as read.",
    responses={
        404: {"model": ErrorResponse, "description": "Notification not found."},
    },
)
async def mark_notification_read(
    notification_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> None:
    await service.mark_read(user_id, notification_id)


@router_notifications.put(
    "/read-all",
    status_code=204,
    summary="Mark all notifications as read",
    description="Marks all notifications for the authenticated user as read.",
)
async def mark_all_notifications_read(
    user_id: UUID = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> None:
    await service.mark_all_read(user_id)


@router_notifications.get(
    "/unread-count",
    summary="Get unread notification count",
    description="Returns the number of unread notifications.",
)
async def get_unread_count(
    user_id: UUID = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> dict:
    page = await service.list(user_id, 1, 1)
    return {"count": page.unread_count}
