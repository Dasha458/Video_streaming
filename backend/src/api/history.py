from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.api.dependencies.services import get_history_service
from src.schemas.endpoint import ErrorResponse, PaginationQuery
from src.schemas.history import HistoryPage
from src.services.auth import get_current_user_id
from src.services.history import HistoryService

router_history = APIRouter(
    prefix="/api/history",
    tags=["history"],
    default_response_class=JSONResponse,
    responses={
        401: {"description": "Not authenticated"},
        500: {"description": "Internal server error"},
    },
)


@router_history.get(
    "",
    response_model=HistoryPage,
    summary="Get watch history",
    description="Returns a paginated list of watched videos for the authenticated user.",
)
async def get_history(
    payload: Annotated[PaginationQuery, Depends()],
    user_id: UUID = Depends(get_current_user_id),
    service: HistoryService = Depends(get_history_service),
) -> HistoryPage:
    items, total = await service.list(user_id, payload.page, payload.size)
    return HistoryPage(items=items, page=payload.page, size=payload.size, total=total)


@router_history.delete(
    "",
    status_code=204,
    summary="Clear watch history",
    description="Removes all watch history entries for the authenticated user.",
)
async def clear_history(
    user_id: UUID = Depends(get_current_user_id),
    service: HistoryService = Depends(get_history_service),
) -> None:
    await service.clear(user_id)


@router_history.delete(
    "/{video_id}",
    status_code=204,
    summary="Remove video from history",
    description="Removes a specific video from the user's watch history.",
    responses={
        404: {"model": ErrorResponse, "description": "History entry not found."},
    },
)
async def remove_from_history(
    video_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: HistoryService = Depends(get_history_service),
) -> None:
    await service.remove(user_id, video_id)
