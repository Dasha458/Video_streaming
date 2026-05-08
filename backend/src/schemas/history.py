from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class HistoryVideoItem(BaseModel):
    id: UUID
    title: str
    thumbnail: str
    channel_name: str
    channel_avatar: str
    views_count: int
    created_at: datetime
    last_watched_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HistoryPage(BaseModel):
    items: List[HistoryVideoItem]
    page: int
    size: int
    total: int
