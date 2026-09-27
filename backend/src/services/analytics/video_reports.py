"""
The per-video deep dive: one video's views, reactions, comments, watch
time, retention curve and traffic sources over a period.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, literal_column, select

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
    Period,
    RetentionBucket,
    TrafficSourceSlice,
    VideoAnalyticsResponse,
)
from src.services.analytics._base import AnalyticsQueries
from src.services.analytics.windowing import (
    _delta,
    _window,
)


class VideoReports(AnalyticsQueries):
    # ---------- PER-VIDEO DEEP-DIVE --------------------------------------

    async def _video_count(
        self,
        video_id: UUID,
        model: Any,
        id_col: Any,
        ts_col: Any,
        since: datetime | None,
        until: datetime | None,
    ) -> int:
        stmt = select(func.count(id_col)).where(model.video_id == video_id)
        return await self._scalar_count(stmt, ts_col, since, until)

    async def _video_reaction_count(
        self,
        video_id: UUID,
        reaction_name: str,
        since: datetime | None,
        until: datetime | None,
    ) -> int:
        base = (
            select(func.count(VideoReaction.id))
            .join(ReactionType, VideoReaction.reaction_type_id == ReactionType.id)
            .where(
                VideoReaction.video_id == video_id, ReactionType.name == reaction_name
            )
        )
        return await self._scalar_count(base, VideoReaction.created_at, since, until)

    async def _video_views_per_day(
        self, video_id: UUID, since: datetime | None
    ) -> list[DailyMetric]:
        return await self._daily_series(
            func.count(VideoView.id),
            VideoView.viewed_at,
            since=since,
            filters=[VideoView.video_id == video_id],
        )

    async def _video_averages(
        self, video_id: UUID, since: datetime | None
    ) -> tuple[float, float]:
        stmt = select(
            func.coalesce(func.avg(VideoWatchSession.watched_seconds), 0),
            func.coalesce(func.avg(VideoWatchSession.completed_percent), 0),
        ).where(VideoWatchSession.video_id == video_id)
        if since is not None:
            stmt = stmt.where(VideoWatchSession.started_at >= since)
        row = (await self.session.execute(stmt)).one()
        return float(row[0] or 0), float(row[1] or 0)

    async def _video_retention_buckets(
        self, video_id: UUID, since: datetime | None
    ) -> list[RetentionBucket]:
        # completed_percent is stored as 0-100. The threshold used to be
        # divided by 100 as if it were a 0.0-1.0 fraction, so every bucket
        # matched any session with more than 0.1 % watched and the retention
        # curve was flat at 100 %.
        buckets: list[RetentionBucket] = []
        for pct in (10, 25, 50, 75, 100):
            stmt = select(func.count(VideoWatchSession.id)).where(
                VideoWatchSession.video_id == video_id,
                VideoWatchSession.completed_percent >= pct,
            )
            if since is not None:
                stmt = stmt.where(VideoWatchSession.started_at >= since)
            buckets.append(
                RetentionBucket(
                    percent=pct,
                    viewers=int((await self.session.execute(stmt)).scalar() or 0),
                )
            )
        return buckets

    async def _video_traffic_sources(
        self, video_id: UUID, since: datetime | None
    ) -> list[TrafficSourceSlice]:
        stmt = (
            select(
                func.coalesce(VideoView.source_type, "unknown").label("src"),
                func.count(VideoView.id).label("cnt"),
            )
            .where(VideoView.video_id == video_id)
            .group_by(literal_column("1"))
            .order_by(func.count(VideoView.id).desc())
        )
        if since is not None:
            stmt = stmt.where(VideoView.viewed_at >= since)
        rows = (await self.session.execute(stmt)).all()
        return self._traffic_slices(rows)

    async def get_video_analytics(
        self,
        channel: Channel,
        video_id: UUID,
        period: Period = Period.LAST_28,
    ) -> VideoAnalyticsResponse | None:
        channel_id = channel.id
        since, prev_since = _window(period)

        video = (
            await self.session.execute(
                select(Video).where(
                    Video.id == video_id, Video.channel_id == channel_id
                )
            )
        ).scalar_one_or_none()
        if video is None:
            return None

        v_cur, v_prev = await self._windowed(
            self._video_count,
            video_id,
            VideoView,
            VideoView.id,
            VideoView.viewed_at,
            since=since,
            prev_since=prev_since,
        )
        c_cur, c_prev = await self._windowed(
            self._video_count,
            video_id,
            Comment,
            Comment.id,
            Comment.created_at,
            since=since,
            prev_since=prev_since,
        )
        l_cur, l_prev = await self._windowed(
            self._video_reaction_count,
            video_id,
            "like",
            since=since,
            prev_since=prev_since,
        )
        d_cur, d_prev = await self._windowed(
            self._video_reaction_count,
            video_id,
            "dislike",
            since=since,
            prev_since=prev_since,
        )

        wt_stmt = select(
            func.coalesce(func.sum(VideoWatchSession.watched_seconds), 0)
        ).where(VideoWatchSession.video_id == video_id)
        wt_cur = await self._scalar_count(
            wt_stmt, VideoWatchSession.started_at, since, None
        )
        wt_prev = (
            await self._scalar_count(
                wt_stmt, VideoWatchSession.started_at, prev_since, since
            )
            if prev_since is not None
            else 0
        )

        avg_duration, avg_percent = await self._video_averages(video_id, since)

        return VideoAnalyticsResponse(
            video_id=video.id,
            title=video.name,
            thumbnail=video.thumbnail_path or "",
            period=period.value,
            views=_delta(v_cur, v_prev),
            likes=_delta(l_cur, l_prev),
            dislikes=_delta(d_cur, d_prev),
            comments=_delta(c_cur, c_prev),
            watch_time_seconds=_delta(wt_cur, wt_prev),
            average_view_duration_seconds=round(avg_duration, 1),
            average_percent_viewed=round(avg_percent, 1),
            views_per_day=await self._video_views_per_day(video_id, since),
            retention=await self._video_retention_buckets(video_id, since),
            traffic_sources=await self._video_traffic_sources(video_id, since),
        )
