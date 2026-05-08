from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.api.dependencies.services import get_playlist_service
from src.schemas.endpoint import ErrorResponse, PaginationQuery
from src.schemas.playlist import PlaylistCreate, PlaylistDetailResponse, PlaylistResponse, PlaylistsPage
from src.services.auth import get_current_user_id
from src.services.playlists import PlaylistService

router_playlists = APIRouter(
    prefix="/api/playlists",
    tags=["playlists"],
    default_response_class=JSONResponse,
    responses={
        401: {"description": "Not authenticated"},
        500: {"description": "Internal server error"},
    },
)


@router_playlists.get(
    "",
    response_model=PlaylistsPage,
    summary="List user playlists",
    description="Returns all playlists owned by the authenticated user.",
)
async def list_playlists(
    user_id: UUID = Depends(get_current_user_id),
    service: PlaylistService = Depends(get_playlist_service),
) -> PlaylistsPage:
    items, total = await service.list_user_playlists(user_id)
    return PlaylistsPage(items=items, total=total)


@router_playlists.post(
    "",
    response_model=PlaylistResponse,
    status_code=201,
    summary="Create playlist",
    description="Creates a new playlist for the authenticated user.",
)
async def create_playlist(
    data: PlaylistCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: PlaylistService = Depends(get_playlist_service),
) -> PlaylistResponse:
    return await service.create(user_id, data.name, data.description)


@router_playlists.get(
    "/{playlist_id}",
    response_model=PlaylistDetailResponse,
    summary="Get playlist with videos",
    description="Returns a playlist with its full video list.",
    responses={
        403: {"model": ErrorResponse, "description": "Playlist not owned by user."},
        404: {"model": ErrorResponse, "description": "Playlist not found."},
    },
)
async def get_playlist(
    playlist_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: PlaylistService = Depends(get_playlist_service),
) -> PlaylistDetailResponse:
    return await service.get_detail(user_id, playlist_id)


@router_playlists.delete(
    "/{playlist_id}",
    status_code=204,
    summary="Delete playlist",
    description="Deletes a playlist owned by the authenticated user.",
    responses={
        403: {"model": ErrorResponse, "description": "Playlist not owned by user."},
        404: {"model": ErrorResponse, "description": "Playlist not found."},
    },
)
async def delete_playlist(
    playlist_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: PlaylistService = Depends(get_playlist_service),
) -> None:
    await service.delete(user_id, playlist_id)


@router_playlists.post(
    "/{playlist_id}/videos",
    status_code=204,
    summary="Add video to playlist",
    description="Adds a video to an owned playlist.",
    responses={
        403: {"model": ErrorResponse, "description": "Playlist not owned by user."},
        404: {"model": ErrorResponse, "description": "Playlist or video not found."},
        409: {"model": ErrorResponse, "description": "Video already in playlist."},
    },
)
async def add_video_to_playlist(
    playlist_id: UUID,
    video_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: PlaylistService = Depends(get_playlist_service),
) -> None:
    await service.add_video(user_id, playlist_id, video_id)


@router_playlists.delete(
    "/{playlist_id}/videos/{video_id}",
    status_code=204,
    summary="Remove video from playlist",
    description="Removes a video from an owned playlist.",
    responses={
        403: {"model": ErrorResponse, "description": "Playlist not owned by user."},
        404: {"model": ErrorResponse, "description": "Playlist or video not found."},
    },
)
async def remove_video_from_playlist(
    playlist_id: UUID,
    video_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: PlaylistService = Depends(get_playlist_service),
) -> None:
    await service.remove_video(user_id, playlist_id, video_id)
