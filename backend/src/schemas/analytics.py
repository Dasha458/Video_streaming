from datetime import datetime
from enum import Enum
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field

# ── Common building blocks ───────────────────────────────────────────────────


class Period(str, Enum):
    """Time window for aggregated metrics (mirrors YouTube Studio presets)."""

    LAST_7 = "7d"
    LAST_28 = "28d"
    LAST_90 = "90d"
    LAST_365 = "365d"
    ALL = "all"

    @property
    def days(self) -> int | None:
        """``None`` means lifetime — callers should skip the time filter."""
        return {
            Period.LAST_7: 7,
            Period.LAST_28: 28,
            Period.LAST_90: 90,
            Period.LAST_365: 365,
            Period.ALL: None,
        }[self]


class DailyMetric(BaseModel):
    date: str  # ISO-8601 "YYYY-MM-DD"
    count: int


class HourlyMetric(BaseModel):
    """Used by real-time (last 48 hours) chart."""

    hour: str  # ISO-8601 "YYYY-MM-DDTHH:00:00Z"
    count: int


class DeltaInt(BaseModel):
    """A metric with its period-over-period delta for trend arrows."""

    value: int
    previous: int
    delta_percent: float  # e.g. +12.5 means +12.5% vs previous period


# ── Overview ────────────────────────────────────────────────────────────────


class TopVideo(BaseModel):
    id: UUID
    title: str
    thumbnail: str
    views_count: int
    likes_count: int
    comments_count: int


class VideoStat(BaseModel):
    id: UUID
    title: str
    thumbnail: str
    privacy: str
    views_count: int
    likes_count: int
    dislikes_count: int
    comments_count: int
    created_at: datetime


class OverviewResponse(BaseModel):
    period: str
    total_views: DeltaInt
    total_subscribers: int
    total_likes: DeltaInt
    total_comments: DeltaInt
    total_watch_time_seconds: DeltaInt
    views_per_day: List[DailyMetric]
    top_videos: List[TopVideo]


# ── Content ─────────────────────────────────────────────────────────────────


class ContentResponse(BaseModel):
    period: str
    videos: List[VideoStat]


# ── Audience ────────────────────────────────────────────────────────────────


class AudienceResponse(BaseModel):
    period: str
    subscribers_per_day: List[DailyMetric]
    unique_viewers: int
    returning_viewers: int
    comments_per_day: List[DailyMetric]


# ── Engagement (YouTube-style watch-time / retention) ───────────────────────


class EngagementResponse(BaseModel):
    period: str
    total_watch_time_seconds: int
    average_view_duration_seconds: float
    average_percent_viewed: float  # 0–100
    engagement_rate: float  # (likes + comments) / views, 0–100
    watch_time_per_day: List[DailyMetric]  # seconds per day
    avg_percent_viewed_per_day: List[DailyMetric]  # 0–100 per day (count field used)


# ── Real-time (last 48 h) ───────────────────────────────────────────────────


class RealtimeResponse(BaseModel):
    views_last_48h: int
    views_last_60min: int
    views_per_hour: List[HourlyMetric]
    top_videos_48h: List[TopVideo]


# ── Traffic sources ─────────────────────────────────────────────────────────


class TrafficSourceSlice(BaseModel):
    source: str  # "direct" | "search" | "recommendation" | "external" | …
    views: int
    percentage: float  # 0–100


class TrafficSourcesResponse(BaseModel):
    period: str
    total_views: int
    sources: List[TrafficSourceSlice]


# ── Per-video deep-dive ─────────────────────────────────────────────────────


class RetentionBucket(BaseModel):
    """Slice of viewers who watched `<=` this percent of the video."""

    percent: int  # 10, 20, … 100
    viewers: int


class VideoAnalyticsResponse(BaseModel):
    video_id: UUID
    title: str
    thumbnail: str
    period: str
    views: DeltaInt
    likes: DeltaInt
    dislikes: DeltaInt
    comments: DeltaInt
    watch_time_seconds: DeltaInt
    average_view_duration_seconds: float
    average_percent_viewed: float
    views_per_day: List[DailyMetric]
    retention: List[RetentionBucket]
    traffic_sources: List[TrafficSourceSlice]


# ── Watch-session heartbeat (input) ─────────────────────────────────────────


class WatchSessionPing(BaseModel):
    """
    Heartbeat sent by the player every ~10 seconds while playback is active.

    The client keeps one stable ``session_id`` (UUID v4) per playback and
    pushes a cumulative ``watched_seconds`` cursor.  Server upserts by id.
    """

    session_id: UUID
    video_id: UUID
    watched_seconds: int = Field(ge=0)
    video_duration_seconds: int = Field(ge=0)
    source_type: str | None = Field(
        default=None,
        max_length=32,
        description=(
            "Optional traffic source tag attached on the first heartbeat: "
            "direct, search, recommendation, external, channel_page, "
            "playlist, subscriptions."
        ),
    )


class WatchSessionAck(BaseModel):
    ok: bool = True
    session_id: UUID
    completed_percent: float
