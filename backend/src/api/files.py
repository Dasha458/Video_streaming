from typing import Annotated
from uuid import UUID

from elasticsearch import AsyncElasticsearch
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    Path,
    Request,
)
from fastapi.responses import JSONResponse, StreamingResponse

from src.api.dependencies.rate_limit import limit_requests
from src.api.dependencies.services import get_file_service, get_upload_service
from src.core.background_tasks import deindex_video_in_es
from src.infrastructure.elasticsearch import get_es_client
from src.schemas.endpoint import (
    ErrorResponse,
    FileMeta,
    FileResponse,
    FileStreamResponse,
)
from src.schemas.uploads import (
    UploadSessionStatus,
    UploadStarted,
    UploadStartRequest,
)
from src.schemas.video import VideoUploadParams
from src.services.dependencies import get_current_user_id
from src.services.files import FileService
from src.services.uploads import UploadService

router_files = APIRouter(
    prefix="/api/files",
    tags=["files"],
    default_response_class=JSONResponse,
    responses={
        404: {"description": "Not found"},
        500: {"description": "Internal server error"},
    },
)


@router_files.post(
    "/uploads",
    response_model=UploadStarted,
    dependencies=[Depends(limit_requests("uploads", max_requests=10, window_seconds=60))],
    summary="Start a resumable upload",
    description=(
        "Opens an upload and returns the id its parts belong to, together "
        "with the part size to use. The file is not sent here."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Not a video, or too large."},
    },
)
async def start_upload(
    payload: UploadStartRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: UploadService = Depends(get_upload_service),
) -> UploadStarted:
    """Begin an upload.

    Videos are uploaded in parts. A 500 MB file sent as one request fails
    entirely on any dropped connection, and forces the gateway to accept
    a body that large from anyone who asks.
    """
    return await service.start(
        user_id=user_id,
        filename=payload.filename,
        content_type=payload.content_type,
        size=payload.size,
    )


@router_files.put(
    "/uploads/{upload_id}/parts/{part_number}",
    response_model=UploadSessionStatus,
    summary="Send one part",
    description=(
        "The body is the raw bytes of this part. Every part but the last "
        "must be exactly the part size the upload reported."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Part is too small."},
        404: {"model": ErrorResponse, "description": "No such upload."},
    },
)
async def upload_part(
    request: Request,
    upload_id: UUID = Path(..., description="Id returned when the upload started."),
    part_number: int = Path(..., ge=1, description="1-based position of this part."),
    user_id: UUID = Depends(get_current_user_id),
    service: UploadService = Depends(get_upload_service),
) -> UploadSessionStatus:
    """Store one part and report everything stored so far.

    Reading the body in full is deliberate: a part is bounded by the part
    size, which is what makes streaming it unnecessary and the gateway's
    body limit small.
    """
    body = await request.body()
    return await service.upload_part(
        upload_id=upload_id,
        user_id=user_id,
        part_number=part_number,
        body=body,
    )


@router_files.get(
    "/uploads/{upload_id}",
    response_model=UploadSessionStatus,
    summary="What has arrived so far",
    description=(
        "Read from storage, not from a counter, so an upload resumed in a "
        "new browser session sends only the parts that are missing."
    ),
    responses={404: {"model": ErrorResponse, "description": "No such upload."}},
)
async def upload_status(
    upload_id: UUID = Path(..., description="Id returned when the upload started."),
    user_id: UUID = Depends(get_current_user_id),
    service: UploadService = Depends(get_upload_service),
) -> UploadSessionStatus:
    return await service.status(upload_id=upload_id, user_id=user_id)


@router_files.post(
    "/uploads/{upload_id}/complete",
    response_model=FileResponse,
    summary="Assemble the parts and create the video",
    description=(
        "Joins the parts into one object, checks its size and hash, then "
        "creates the video and queues encoding."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Nothing arrived, or the wrong size."},
        404: {"model": ErrorResponse, "description": "No such upload."},
        409: {"model": ErrorResponse, "description": "This file is already on the platform."},
    },
)
async def complete_upload(
    payload: Annotated[VideoUploadParams, Form()],
    upload_id: UUID = Path(..., description="Id returned when the upload started."),
    user_id: UUID = Depends(get_current_user_id),
    service: UploadService = Depends(get_upload_service),
) -> FileResponse:
    """Finish an upload.

    The title, description and thumbnail travel here rather than at the
    start: they are what the uploader fills in while the bytes are
    already on their way.
    """
    return await service.complete(
        upload_id=upload_id,
        user_id=user_id,
        name=payload.name,
        description=payload.description,
        privacy=payload.privacy,
        category=payload.category,
        thumbnail=payload.thumbnail,
    )


@router_files.delete(
    "/uploads/{upload_id}",
    status_code=204,
    summary="Give up on an upload",
    description=(
        "Releases the parts already sent. Worth calling: an unfinished "
        "multipart upload holds them and appears in no object listing."
    ),
    responses={404: {"model": ErrorResponse, "description": "No such upload."}},
)
async def abort_upload(
    upload_id: UUID = Path(..., description="Id returned when the upload started."),
    user_id: UUID = Depends(get_current_user_id),
    service: UploadService = Depends(get_upload_service),
) -> None:
    await service.abort(upload_id=upload_id, user_id=user_id)


@router_files.get(
    "/videos/{video_id}/download",
    response_model=FileStreamResponse,
    dependencies=[
        Depends(limit_requests("download_video", max_requests=5, window_seconds=60))
    ],
    summary="Download a stored video file",
    description="Streams a video file stored in object storage as a binary response.",
    response_description="Binary stream of the requested file.",
    responses={
        200: {
            "model": FileStreamResponse,
            "description": "File streaming response.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Requested file was not found.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Unexpected error occurred while retrieving the file.",
        },
    },
)
async def get_file(
    video_id: UUID = Path(..., description="UUID of the video to download."),
    user_id: UUID = Depends(get_current_user_id),
    service: FileService = Depends(get_file_service),
) -> StreamingResponse:
    """
    Downloads the video as a single MP4 file.

    There is one downloadable file per video, built by the converter at
    encode time. The resolution parameter this used to accept could only
    return an HLS playlist named .mp4, so it is gone rather than fixed.
    Only the video's owner may download it.
    """
    object_key, filename, media_type = await service.get_video_file(video_id, user_id)
    chunk_gen = service.stream_file(object_key, bucket_name="videos")

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(chunk_gen, media_type=media_type, headers=headers)


@router_files.delete(
    "/videos/{video_id}",
    response_model=FileResponse,
    dependencies=[
        Depends(limit_requests("delete_video", max_requests=5, window_seconds=60))
    ],
    summary="Delete a video and its assets",
    description=(
        "Deletes a video entry from the database and removes all its related files "
        "(HLS streams, thumbnails) from object storage."
    ),
    responses={
        200: {"model": FileResponse, "description": "Video successfully deleted."},
        400: {
            "model": ErrorResponse,
            "description": "Invalid request or unauthorized.",
        },
        404: {"model": ErrorResponse, "description": "Video not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
    },
)
async def delete_files(
    background_tasks: BackgroundTasks,
    video_id: UUID = Path(..., description="UUID of the video to delete."),
    user_id: UUID = Depends(get_current_user_id),
    service: FileService = Depends(get_file_service),
    es: "AsyncElasticsearch" = Depends(get_es_client),
) -> FileResponse:
    """
    Delete a video, its database record, and all associated storage files.
    """
    video = await service.delete_video(video_id, user_id)
    background_tasks.add_task(deindex_video_in_es, str(video_id), es)

    return FileResponse(
        status="deleted",
        files=[
            FileMeta(
                file_id=video_id,
                filename=video.name,
                size=video.size,
            )
        ],
    )
