"""
Shared plumbing for the analytics reports.

Every report needs the same few things: a channel lookup, a way to run a
counter over the current window and the one before it, a scalar count with
optional time bounds, and a bucket-by-day series. They live here so the
report modules are about their own questions and not about SQL mechanics.
"""

from datetime import datetime
from typing import Any, Awaitable, Callable, Sequence
from uuid import UUID

from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    Channel,
    Comment,
    ReactionType,
    Video,
    VideoReaction,
    VideoView,
    VideoWatchSession,
)
from src.schemas.analytics import (
    DailyMetric,
    TrafficSourceSlice,
)
from src.services.analytics.windowing import (
    _fill_daily,
)


class AnalyticsQueries:
    """Base for the report modules: owns the session and the shared queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------- channel lookup -------------------------------------------

    async def get_channel(self, user_id: UUID) -> Channel | None:
        result = await self.session.execute(
            select(Channel).where(Channel.user_id == user_id)
        )
        return result.scalar_one_or_none()

    # ---------- current-vs-previous-window helper -------------------------
    #
    # Every period-aware metric in this service needs the same shape: run a
    # counter for the current window, and (unless the period is "all") run
    # it again for the immediately preceding window of equal size. This one
    # helper replaces what used to be ~7 near-identical
    # "current = await X(...); previous = await X(...) if prev_since else 0"
    # blocks scattered across get_overview() and get_video_analytics().

    @staticmethod
    async def _windowed(
        count_fn: Callable[..., Awaitable[int]],
        *args: Any,
        since: datetime | None,
        prev_since: datetime | None,
    ) -> tuple[int, int]:
        """Call ``count_fn(*args, since, until)`` for the current window and,
        if a preceding window exists, for that one too."""
        current = await count_fn(*args, since, None)
        if prev_since is None:
            return current, 0
        previous = await count_fn(*args, prev_since, since)
        return current, previous

    # ---------- low-level scalar helpers (channel-scoped) -----------------

    async def _scalar_count(
        self,
        base_stmt: Any,
        ts_col: Any,
        since: datetime | None,
        until: datetime | None,
    ) -> int:
        stmt = base_stmt
        if since is not None:
            stmt = stmt.where(ts_col >= since)
        if until is not None:
            stmt = stmt.where(ts_col < until)
        return int((await self.session.execute(stmt)).scalar() or 0)

    async def _count_views(
        self,
        channel_id: UUID,
        since: datetime | None,
        until: datetime | None = None,
    ) -> int:
        stmt = (
            select(func.count(VideoView.id))
            .join(Video, VideoView.video_id == Video.id)
            .where(Video.channel_id == channel_id)
        )
        return await self._scalar_count(stmt, VideoView.viewed_at, since, until)

    async def _count_reactions(
        self,
        channel_id: UUID,
        reaction_name: str,
        since: datetime | None,
        until: datetime | None = None,
    ) -> int:
        stmt = (
            select(func.count(VideoReaction.id))
            .join(Video, VideoReaction.video_id == Video.id)
            .join(ReactionType, VideoReaction.reaction_type_id == ReactionType.id)
            .where(Video.channel_id == channel_id, ReactionType.name == reaction_name)
        )
        return await self._scalar_count(stmt, VideoReaction.created_at, since, until)

    async def _count_comments(
        self,
        channel_id: UUID,
        since: datetime | None,
        until: datetime | None = None,
    ) -> int:
        stmt = (
            select(func.count(Comment.id))
            .join(Video, Comment.video_id == Video.id)
            .where(Video.channel_id == channel_id)
        )
        return await self._scalar_count(stmt, Comment.created_at, since, until)

    async def _sum_watch_time(
        self,
        channel_id: UUID,
        since: datetime | None,
        until: datetime | None = None,
    ) -> int:
        stmt = (
            select(func.coalesce(func.sum(VideoWatchSession.watched_seconds), 0))
            .join(Video, VideoWatchSession.video_id == Video.id)
            .where(Video.channel_id == channel_id)
        )
        return await self._scalar_count(
            stmt, VideoWatchSession.started_at, since, until
        )

    # ---------- daily series helper --------------------------------------
    #
    # Six queries in this file had the same shape: bucket rows by calendar
    # day, aggregate them, order by the day, optionally cut off at `since`,
    # then pad the gaps. Only the aggregate, the timestamp column and the
    # joins differed. Writing it once means a change to how a day is
    # bucketed cannot apply to five places and miss the sixth.

    async def _daily_series(
        self,
        aggregate: Any,
        ts_col: Any,
        *,
        since: datetime | None,
        joins: Sequence[tuple[Any, Any]] = (),
        filters: Sequence[Any] = (),
        transform: Callable[[Any], int] = int,
    ) -> list[DailyMetric]:
        stmt = select(func.date(ts_col).label("day"), aggregate.label("val"))
        for target, onclause in joins:
            stmt = stmt.join(target, onclause)
        if filters:
            stmt = stmt.where(*filters)
        if since is not None:
            stmt = stmt.where(ts_col >= since)
        stmt = stmt.group_by(literal_column("1")).order_by(literal_column("1"))

        rows = (await self.session.execute(stmt)).all()
        return _fill_daily([(r.day, transform(r.val)) for r in rows], since)

    # Shared by the channel-wide traffic panel and the per-video one.
    @staticmethod
    def _traffic_slices(rows: Any) -> list[TrafficSourceSlice]:
        total = sum(int(r.cnt) for r in rows) or 1  # avoid div/0
        return [
            TrafficSourceSlice(
                source=r.src or "unknown",
                views=int(r.cnt),
                percentage=round(int(r.cnt) / total * 100, 1),
            )
            for r in rows
        ]
