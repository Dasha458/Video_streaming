from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=50, description="Unique channel name")
    description: Optional[str] = Field(None, max_length=500)


class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=50)
    description: Optional[str] = Field(None, max_length=500)


class ChannelResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    subscribers_count: int
    views_count: int
    avatar_path: Optional[str]
    background_path: Optional[str]
    created_at: datetime
    channel_avatar: Optional[str] = None
    channel_name: str = ""
    channelBanner: Optional[str] = None
    subscribersCount: int = 0
    videosCount: int = 0
    bio: Optional[str] = None
    createdAt: str = ""
    isOwner: bool = False

    model_config = ConfigDict(from_attributes=True)


class ChannelSubscriptionItem(BaseModel):
    channel_name: str
    channel_avatar: Optional[str]
    subscribersCount: int
    videosCount: int
    createdAt: str

    model_config = ConfigDict(from_attributes=True)
