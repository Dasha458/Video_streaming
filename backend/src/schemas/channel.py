from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChannelCreate(BaseModel):
    name: str = Field(
        ..., min_length=3, max_length=50, description="Unique channel name"
    )
    description: Optional[str] = Field(None, max_length=500)


class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=50)
    description: Optional[str] = Field(None, max_length=500)


class ChannelResponse(BaseModel):
    """One channel, with one name per value.

    This used to carry eighteen fields for what is six pieces of
    information, because every value appeared twice under two
    conventions -- name/channel_name, avatar_path/channel_avatar,
    background_path/channelBanner, subscribers_count/subscribersCount,
    description/bio, and created_at as both a datetime and a string. The
    builder filled both halves of each pair from the same source, and the
    frontend read `subscribersCount ?? subscribers_count ?? 0` because
    nothing said which one would arrive. Changing where a value came from
    meant remembering to change it in two places.

    snake_case throughout, like the rest of the API.
    """

    id: UUID
    name: str
    description: Optional[str]
    subscribers_count: int
    views_count: int
    videos_count: int = 0
    avatar_path: Optional[str]
    background_path: Optional[str]
    created_at: datetime
    is_owner: bool = False
    is_subscribed: bool = False

    model_config = ConfigDict(from_attributes=True)


class ChannelSubscriptionItem(BaseModel):
    """The smaller shape the subscriptions list returns."""

    name: str
    avatar_path: Optional[str]
    subscribers_count: int
    videos_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
