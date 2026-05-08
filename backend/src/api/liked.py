from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.api.dependencies.services import get_liked_service
from src.schemas.endpoint import PaginationQuery
from src.schemas.video import VideoPreviewPage
from src.services.auth import get_current_user_id
from src.services.liked import LikedService

router_liked = APIRouter(
    prefix="/api/liked",
    tags=["liked"],
    default_response_class=JSONResponse,
    responses={
        401: {"description": "Not authenticated"},
        500: {"description": "Internal server error"},
    },
)


@router_liked.get(
    "",
    response_model=VideoPreviewPage,
    summary="Get liked videos",
    description="Returns a paginated list of videos the authenticated user has liked.",
)
async def get_liked_videos(
    payload: Annotated[PaginationQuery, Depends()],
    user_id: UUID = Depends(get_current_user_id),
    service: LikedService = Depends(get_liked_service),
) -> VideoPreviewPage:
    items, total = await service.list_liked(user_id, payload.page, payload.size)
    return VideoPreviewPage(items=items, page=payload.page, size=payload.size, total=total)
