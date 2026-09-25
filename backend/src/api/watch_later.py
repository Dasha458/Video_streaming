from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.api.dependencies.services import get_watch_later_service
from src.schemas.endpoint import ErrorResponse, PaginationQuery
from src.schemas.watch_later import WatchLaterPage
from src.services.dependencies import get_current_user_id
from src.services.watch_later import WatchLaterService

router_watch_later = APIRouter(
    prefix="/api/watch-later",
    tags=["watch-later"],
    default_response_class=JSONResponse,
    responses={
        401: {"description": "Not authenticated"},
        500: {"description": "Internal server error"},
    },
)


@router_watch_later.get(
    "",
    response_model=WatchLaterPage,
    summary="Get watch later list",
    description="Returns a paginated list of videos saved to watch later.",
)
async def get_watch_later(
    payload: Annotated[PaginationQuery, Depends()],
    user_id: UUID = Depends(get_current_user_id),
    service: WatchLaterService = Depends(get_watch_later_service),
) -> WatchLaterPage:
    items, total = await service.list(user_id, payload.page, payload.size)
    return WatchLaterPage(
        items=items, page=payload.page, size=payload.size, total=total
    )


@router_watch_later.post(
    "/{video_id}",
    status_code=204,
    summary="Add video to watch later",
    description="Saves a video to the user's watch later list.",
    responses={
        409: {"model": ErrorResponse, "description": "Video already in watch later."},
    },
)
async def add_to_watch_later(
    video_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: WatchLaterService = Depends(get_watch_later_service),
) -> None:
    await service.add(user_id, video_id)


@router_watch_later.delete(
    "",
    status_code=204,
    summary="Clear watch later list",
    description="Removes all videos from the user's watch later list.",
)
async def clear_watch_later(
    user_id: UUID = Depends(get_current_user_id),
    service: WatchLaterService = Depends(get_watch_later_service),
) -> None:
    await service.clear(user_id)


@router_watch_later.delete(
    "/{video_id}",
    status_code=204,
    summary="Remove video from watch later",
    description="Removes a specific video from the user's watch later list.",
    responses={
        404: {"model": ErrorResponse, "description": "Watch later entry not found."},
    },
)
async def remove_from_watch_later(
    video_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: WatchLaterService = Depends(get_watch_later_service),
) -> None:
    await service.remove(user_id, video_id)
