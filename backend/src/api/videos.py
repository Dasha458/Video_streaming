from typing import TYPE_CHECKING, Annotated, List
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Path,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse

from src.api.dependencies.services import get_stream_service, get_video_service
from src.core.background_tasks import set_video_privacy_in_es
from src.infrastructure.elasticsearch import get_es_client
from src.schemas.endpoint import ErrorResponse, PaginationQuery
from src.schemas.files import SignedUrlResponse
from src.schemas.privacy import PrivacyLevel, PrivacyResponse
from src.schemas.reaction import ReactionRequest, ReactionResponse
from src.schemas.video import (
    StreamUrlResponse,
    VideoCategory,
    VideoPage,
    VideoPlayback,
    VideoPreviewPage,
)
from src.services.dependencies import get_current_user_id, get_optional_user_id
from src.services.streaming import StreamService
from src.services.videos import VideoService
from src.services.viewer_identity import viewer_key

if TYPE_CHECKING:
    from elasticsearch import AsyncElasticsearch

router_videos = APIRouter(
    prefix="/api/videos",
    tags=["videos"],
    default_response_class=JSONResponse,
    responses={
        404: {"description": "Not found"},
        500: {"description": "Internal server error"},
    },
)


@router_videos.get(
    "/stream-authorize",
    include_in_schema=False,
    summary="Authorise one media object (gateway use)",
)
async def stream_authorize(
    file_path: Annotated[
        str, Query(description="Gateway path of the object being requested.")
    ],
    user_id: UUID | None = Depends(get_optional_user_id),
    service: StreamService = Depends(get_stream_service),
) -> JSONResponse:
    """Called by the gateway for every playlist and segment request.

    This is what replaced ``/api/files/sign_url``. That endpoint signed
    whatever path it was handed, without asking who wanted it or what it
    belonged to. This one reads the video id out of the object key and
    applies the same privacy rule as the watch page, so a path the caller
    may not watch is refused instead of signed.
    """
    result = await service.authorize_media(file_path, user_id)
    return JSONResponse(
        content=SignedUrlResponse(**result).model_dump(),
        headers={"X-Signed-Url": result["signed_url"]},
    )


@router_videos.get(
    "/{video_id}/stream-url",
    response_model=StreamUrlResponse,
    summary="Get the playable URL for a video",
    description=(
        "Checks the video's privacy against the caller and returns the URL "
        "its player should load. Pass `redirect=true` to be sent there with "
        "a 302 instead."
    ),
    responses={
        200: {"model": StreamUrlResponse, "description": "URL issued."},
        302: {"description": "Redirected to the stream, when redirect=true."},
        404: {
            "model": ErrorResponse,
            "description": (
                "No such video, or the caller may not watch it. The two are "
                "answered the same way so the response does not confirm that "
                "a private video exists."
            ),
        },
    },
)
async def get_stream_url(
    video_id: UUID,
    redirect: Annotated[
        bool, Query(description="Answer with a 302 to the stream instead of JSON.")
    ] = False,
    user_id: UUID | None = Depends(get_optional_user_id),
    service: StreamService = Depends(get_stream_service),
) -> Response:
    url, expires_in = await service.stream_url(video_id, user_id)
    if redirect:
        return RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    return JSONResponse(
        content=StreamUrlResponse(url=url, expires_in=expires_in).model_dump()
    )


@router_videos.get(
    "/",
    response_model=VideoPreviewPage,
    summary="List all videos",
    description="Returns a paginated list of videos with metadata such as title, duration, and status.",
    response_description="A paginated list of videos.",
    responses={
        200: {
            "model": VideoPreviewPage,
            "description": "List of videos successfully retrieved.",
        },
        400: {
            "model": ErrorResponse,
            "description": "Invalid query parameters (e.g., invalid page/size).",
        },
        500: {
            "model": ErrorResponse,
            "description": "Internal server error.",
        },
    },
)
async def get_videos(
    payload: Annotated[PaginationQuery, Depends()],
    channel_name: str | None = Query(
        default=None, description="Filter videos by channel name"
    ),
    service: VideoService = Depends(get_video_service),
) -> VideoPreviewPage:
    videos, total = await service.list_videos(
        page=payload.page, size=payload.size, channel_name=channel_name
    )
    return VideoPreviewPage(
        items=videos, page=payload.page, size=payload.size, total=total
    )


@router_videos.get(
    "/categories",
    response_model=List[str],
    summary="List all videos of categories",
    description="Returns a list of distinct video category Name.",
    response_description="List of unique category Name.",
    responses={
        200: {
            "model": List[str],
            "description": "List of categories successfully retrieved.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Internal server error.",
        },
    },
)
async def get_categories(
    service: VideoService = Depends(get_video_service),
    plain: bool = Query(True, description="Return plain list of category names"),
) -> List[str]:
    return await service.list_categories(plain=plain)


@router_videos.get(
    "/{video_id}",
    response_model=VideoPlayback,
    summary="Get video playback information",
    description="Retrieves metadata and playback details for a specific video.",
    response_description="Metadata describing the requested video.",
    responses={
        200: {
            "model": VideoPlayback,
            "description": "Video metadata retrieved successfully.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Video metadata could not be found.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Unexpected error occurred while retrieving metadata.",
        },
    },
)
async def get_video_info(
    request: Request,
    video_id: UUID = Path(
        ..., description="UUID of the video to retrieve playback info for."
    ),
    source: str | None = Query(
        default=None,
        max_length=32,
        description=(
            "Traffic source hint tagged on the resulting VideoView: "
            "direct | search | recommendation | external | channel_page | "
            "playlist | subscriptions."
        ),
    ),
    user_id: UUID | None = Depends(get_optional_user_id),
    service: VideoService = Depends(get_video_service),
) -> VideoPlayback:
    return await service.get_playback(
        video_id=video_id,
        user_id=user_id,
        source_type=source,
        # A view is one viewer, so the request has to say which viewer.
        viewer_key=viewer_key(request, user_id),
    )


@router_videos.get(
    "/categories/{category}",
    response_model=VideoPreviewPage,
    summary="List all videos by category",
    description="Returns a paginated list of videos by category.",
    response_description="A paginated list of videos by category.",
    responses={
        200: {
            "model": VideoPreviewPage,
            "description": "List of videos successfully retrieved.",
        },
        400: {
            "model": ErrorResponse,
            "description": "Invalid query parameters (e.g., invalid page/size).",
        },
        500: {
            "model": ErrorResponse,
            "description": "Internal server error.",
        },
    },
)
async def get_videos_category(
    query: Annotated[PaginationQuery, Depends()],
    category: VideoCategory = Path(description="Category of videos to filter by."),
    service: VideoService = Depends(get_video_service),
) -> VideoPreviewPage:
    videos, total = await service.list_videos(
        page=query.page, size=query.size, category=category
    )
    return VideoPreviewPage(items=videos, page=query.page, size=query.size, total=total)


@router_videos.post(
    "/{video_id}/reactions",
    response_model=ReactionResponse,
    summary="Change video reaction",
    description="Adds or removes a user's reaction (like, love, funny, etc.) to a specific video.",
    response_description="Updated like and dislike counts for the video.",
    responses={
        200: {
            "model": VideoPage,
            "description": "Reactions successfully retrieved.",
        },
        400: {
            "model": ErrorResponse,
            "description": "Invalid parameters (e.g., invalid like/dislike count).",
        },
        500: {
            "model": ErrorResponse,
            "description": "Internal server error.",
        },
    },
)
async def react_to_video(
    video_id: UUID,
    payload: ReactionRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: VideoService = Depends(get_video_service),
) -> ReactionResponse:
    counts = await service.react(video_id, user_id, payload.reaction_name)
    return ReactionResponse(
        target_id=video_id,
        target_type="video",
        reactions=counts,
    )


@router_videos.patch(
    "/{video_id}/privacy",
    summary="Update video privacy",
    response_model=PrivacyResponse,
    description="Update the privacy visibility of the specified video (public/private).",
    response_description="Updated PrivacyLevel setting.",
    responses={
        200: {
            "model": PrivacyResponse,
            "description": "PrivacyLevel successfully updated.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Not allowed to update this resource.",
        },
        404: {"model": ErrorResponse, "description": "Video not found."},
        500: {"model": ErrorResponse, "description": "Internal server error."},
    },
)
async def update_privacy(
    video_id: UUID,
    background_tasks: BackgroundTasks,
    updated_privacy: PrivacyLevel = Query(
        default="public",
        description="Privacy setting: `public` or `private`",
        examples=["public", "private"],
    ),
    user_id: UUID = Depends(get_current_user_id),
    service: VideoService = Depends(get_video_service),
    es: "AsyncElasticsearch" = Depends(get_es_client),
) -> PrivacyResponse:
    old_privacy, new_privacy = await service.update_privacy(
        video_id=video_id, user_id=user_id, privacy_name=updated_privacy
    )
    # Nothing used to tell the search index about this, so a video switched
    # to private kept its public document and stayed searchable.
    background_tasks.add_task(set_video_privacy_in_es, str(video_id), new_privacy, es)
    return PrivacyResponse(
        video_id=video_id,
        old_privacy=old_privacy,
        updated_privacy=new_privacy,
    )
