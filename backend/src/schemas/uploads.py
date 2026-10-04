from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class UploadStartRequest(BaseModel):
    """What the client knows before it has sent anything."""

    filename: str = Field(..., max_length=512, description="Original file name.")
    content_type: str = Field(
        ..., max_length=255, description="MIME type; must be video/*."
    )
    size: int = Field(
        ...,
        gt=0,
        description=(
            "Size of the file in bytes. A claim: it decides whether the "
            "upload may start, and is checked again against the assembled "
            "object before the video is created."
        ),
    )


class UploadStarted(BaseModel):
    upload_id: UUID = Field(..., description="Identifies this upload from now on.")
    part_size: int = Field(
        ..., description="Size of every part but the last, in bytes."
    )
    total_parts: int = Field(..., description="How many parts that works out to.")


class UploadSessionStatus(BaseModel):
    """What storage holds, so an interrupted upload can send only the rest."""

    upload_id: UUID
    part_size: int
    declared_size: int
    received_parts: List[int] = Field(
        default_factory=list,
        description=(
            "Part numbers already stored. Read from storage rather than "
            "from a counter, because storage is what decides whether a "
            "part exists."
        ),
    )
    received_bytes: int = Field(
        0, description="Total size of those parts, for a progress bar."
    )


class UploadPartAccepted(BaseModel):
    part_number: int
    received_parts: List[int]
    received_bytes: int
