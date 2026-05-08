from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas.video import VideoPreview


class PlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Playlist name cannot be empty")
        return v.strip()


class PlaylistResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    created_at: datetime
    video_count: int

    model_config = ConfigDict(from_attributes=True)


class PlaylistDetailResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    created_at: datetime
    items: List[VideoPreview] = Field(default_factory=list)
    total: int

    model_config = ConfigDict(from_attributes=True)


class PlaylistsPage(BaseModel):
    items: List[PlaylistResponse]
    total: int
