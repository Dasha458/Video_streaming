"""
Creator analytics service.

Provides YouTube-Studio-style aggregations over the channel's content:
  * overview, content, audience
  * engagement (watch-time, retention, engagement rate)
  * real-time (last 48 h, last 60 min)
  * traffic sources (breakdown by ``VideoView.source_type``)
  * per-video deep-dive
  * watch-session heartbeat upsert

All period-aware queries accept a :class:`~src.schemas.analytics.Period`
enum value ("7d" / "28d" / "90d" / "365d" / "all").  Delta metrics always
compare the current window with the immediately preceding one of equal
size (for "all", the previous window is considered empty).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Sequence
from uuid import UUID

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.status_ids import PRIVACY_PUBLIC_ID
from src.models import (
    Channel,
    Comment,
    ReactionType,
    Subscription,
    Video,
    VideoReaction,
    VideoView,
    VideoWatchSession,
)
from src.schemas.analytics import (
    AudienceResponse,
    ContentResponse,
    DailyMetric,
    DeltaInt,
    EngagementResponse,
    HourlyMetric,
    OverviewResponse,
    Period,
    RealtimeResponse,
    RetentionBucket,
    TopVideo,
    TrafficSourceSlice,
    TrafficSourcesResponse,
    VideoAnalyticsResponse,
    VideoStat,
    WatchSessionAck,
    WatchSessionPing,
)

# ── Internal helpers ────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _window(period: Period) -> tuple[datetime | None, datetime | None]:
    """
    Returns (current_since, previous_since).

    * current window: ``[current_since, now]``
    * previous window: ``[previous_since, current_since)``

    For ``Period.ALL`` both values are ``None`` (no time filter).
    """
    days = period.days
    if days is None:
        return None, None
    now = _now()
    current = now - timedelta(days=days)
    previous = now - timedelta(days=days * 2)
    return current, previous


def _pct_delta(current: int, previous: int) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) / previous * 100, 1)


def _delta(current: int, previous: int) -> DeltaInt:
    return DeltaInt(
        value=int(current),
        previous=int(previous),
        delta_percent=_pct_delta(int(current), int(previous)),
    )


def _fill_daily(rows: Sequence[tuple], since: datetime | None) -> list[DailyMetric]:
    """Ensure days with zero activity still appear in the series."""
    known = {str(r[0]): int(r[1]) for r in rows}
    if since is None:
        return [DailyMetric(date=d, count=c) for d, c in sorted(known.items())]
    out: list[DailyMetric] = []
    cursor = since.date()
    today = _now().date()
    while cursor <= today:
        key = cursor.isoformat()
        out.append(DailyMetric(date=key, count=known.get(key, 0)))
        cursor += timedelta(days=1)
    return out


# ── Service ────────────────────────────────────────────────────────────────


class AnalyticsService:
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
        try:
            return await self._scalar_count(
                stmt, VideoReaction.created_at, since, until
            )
        except Exception:
            # Fallback: VideoReaction may lack created_at in some deployments —
            # in that case we simply return the lifetime counter.
            fallback = (
                select(func.coalesce(func.sum(Video.likes_count), 0))
                if reaction_name == "like"
                else select(func.coalesce(func.sum(Video.dislikes_count), 0))
            )
            fallback = fallback.where(Video.channel_id == channel_id)
            return int((await self.session.execute(fallback)).scalar() or 0)

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
        return await self._scalar_count(stmt, VideoWatchSession.started_at, since, until)

    # ---------- OVERVIEW -------------------------------------------------

    async def _overview_views_per_day(
        self, channel_id: UUID, since: datetime | None
    ) -> list[DailyMetric]:
        stmt = (
            select(
                func.date(VideoView.viewed_at).label("day"),
                func.count(VideoView.id).label("cnt"),
            )
            .join(Video, VideoView.video_id == Video.id)
            .where(Video.channel_id == channel_id)
            .group_by(literal_column("1"))
            .order_by(literal_column("1"))
        )
        if since is not None:
            stmt = stmt.where(VideoView.viewed_at >= since)
        rows = (await self.session.execute(stmt)).all()
        return _fill_daily([(r.day, r.cnt) for r in rows], since)

    async def _overview_top_videos(
        self, channel_id: UUID, since: datetime | None, limit: int = 5
    ) -> list[TopVideo]:
        stmt = (
            select(
                Video.id,
                Video.name,
                Video.thumbnail_path,
                func.count(VideoView.id).label("vc"),
                Video.likes_count,
                func.count(Comment.id.distinct()).label("cc"),
            )
            .outerjoin(VideoView, VideoView.video_id == Video.id)
            .outerjoin(Comment, Comment.video_id == Video.id)
            .where(Video.channel_id == channel_id)
            .group_by(Video.id)
            .order_by(func.count(VideoView.id).desc())
            .limit(limit)
        )
        if since is not None:
            stmt = stmt.where(
                (VideoView.viewed_at >= since) | (VideoView.viewed_at.is_(None))
            )
        rows = (await self.session.execute(stmt)).all()
        return [
            TopVideo(
                id=r.id,
                title=r.name,
                thumbnail=r.thumbnail_path or "",
                views_count=int(r.vc or 0),
                likes_count=int(r.likes_count or 0),
                comments_count=int(r.cc or 0),
            )
            for r in rows
        ]

    async def get_overview(
        self, channel: Channel, period: Period = Period.LAST_28
    ) -> OverviewResponse:
        channel_id = channel.id
        since, prev_since = _window(period)

        views, prev_views = await self._windowed(
            self._count_views, channel_id, since=since, prev_since=prev_since
        )
        likes, prev_likes = await self._windowed(
            self._count_reactions,
            channel_id,
            "like",
            since=since,
            prev_since=prev_since,
        )
        comments, prev_comments = await self._windowed(
            self._count_comments, channel_id, since=since, prev_since=prev_since
        )
        watch_time, prev_watch = await self._windowed(
            self._sum_watch_time, channel_id, since=since, prev_since=prev_since
        )

        return OverviewResponse(
            period=period.value,
            total_views=_delta(views, prev_views),
            total_subscribers=int(channel.subscribers_count or 0),
            total_likes=_delta(likes, prev_likes),
            total_comments=_delta(comments, prev_comments),
            total_watch_time_seconds=_delta(watch_time, prev_watch),
            views_per_day=await self._overview_views_per_day(channel_id, since),
            top_videos=await self._overview_top_videos(channel_id, since),
        )

    # ---------- CONTENT --------------------------------------------------

    async def get_content(
        self, channel: Channel, period: Period = Period.LAST_28
    ) -> ContentResponse:
        channel_id = channel.id
        result = await self.session.execute(
            select(
                Video.id,
                Video.name,
                Video.thumbnail_path,
                Video.privacy_id,
                Video.views_count,
                Video.likes_count,
                Video.dislikes_count,
                Video.created_at,
                func.count(Comment.id).label("comments_count"),
            )
            .outerjoin(Comment, Comment.video_id == Video.id)
            .where(Video.channel_id == channel_id)
            .group_by(Video.id)
            .order_by(Video.created_at.desc())
        )
        videos = [
            VideoStat(
                id=r.id,
                title=r.name,
                thumbnail=r.thumbnail_path or "",
                privacy="public" if r.privacy_id == PRIVACY_PUBLIC_ID else "private",
                views_count=int(r.views_count or 0),
                likes_count=int(r.likes_count or 0),
                dislikes_count=int(r.dislikes_count or 0),
                comments_count=int(r.comments_count or 0),
                created_at=r.created_at,
            )
            for r in result.all()
        ]
        return ContentResponse(period=period.value, videos=videos)

    # ---------- AUDIENCE -------------------------------------------------

    async def get_audience(
        self, channel: Channel, period: Period = Period.LAST_28
    ) -> AudienceResponse:
        channel_id = channel.id
        since, _ = _window(period)

        subs_stmt = (
            select(
                func.date(Subscription.created_at).label("day"),
                func.count(Subscription.subscriber_id).label("cnt"),
            )
            .where(Subscription.channel_id == channel_id)
            .group_by(literal_column("1"))
            .order_by(literal_column("1"))
        )
        if since is not None:
            subs_stmt = subs_stmt.where(Subscription.created_at >= since)
        subs_rows = (await self.session.execute(subs_stmt)).all()
        subscribers_per_day = _fill_daily([(r.day, r.cnt) for r in subs_rows], since)

        unique_stmt = (
            select(func.count(func.distinct(VideoView.user_id)))
            .join(Video, VideoView.video_id == Video.id)
            .where(Video.channel_id == channel_id, VideoView.user_id.isnot(None))
        )
        if since is not None:
            unique_stmt = unique_stmt.where(VideoView.viewed_at >= since)
        unique_viewers = int((await self.session.execute(unique_stmt)).scalar() or 0)

        returning_stmt = select(func.count()).select_from(
            select(VideoView.user_id)
            .join(Video, VideoView.video_id == Video.id)
            .where(Video.channel_id == channel_id, VideoView.user_id.isnot(None))
            .group_by(VideoView.user_id)
            .having(func.count(VideoView.id) > 1)
            .subquery()
        )
        returning_viewers = int(
            (await self.session.execute(returning_stmt)).scalar() or 0
        )

        cmts_stmt = (
            select(
                func.date(Comment.created_at).label("day"),
                func.count(Comment.id).label("cnt"),
            )
            .join(Video, Comment.video_id == Video.id)
            .where(Video.channel_id == channel_id)
            .group_by(literal_column("1"))
            .order_by(literal_column("1"))
        )
        if since is not None:
            cmts_stmt = cmts_stmt.where(Comment.created_at >= since)
        cmts_rows = (await self.session.execute(cmts_stmt)).all()
        comments_per_day = _fill_daily([(r.day, r.cnt) for r in cmts_rows], since)

        return AudienceResponse(
            period=period.value,
            subscribers_per_day=subscribers_per_day,
            unique_viewers=unique_viewers,
            returning_viewers=returning_viewers,
            comments_per_day=comments_per_day,
        )

    # ---------- ENGAGEMENT (watch time / retention) ----------------------

    async def get_engagement(
        self, channel: Channel, period: Period = Period.LAST_28
    ) -> EngagementResponse:
        channel_id = channel.id
        since, _ = _window(period)

        total_watch = await self._sum_watch_time(channel_id, since)

        # Avg view duration & avg % viewed
        avg_stmt = (
            select(
                func.coalesce(func.avg(VideoWatchSession.watched_seconds), 0),
                func.coalesce(func.avg(VideoWatchSession.completed_percent), 0),
            )
            .join(Video, VideoWatchSession.video_id == Video.id)
            .where(Video.channel_id == channel_id)
        )
        if since is not None:
            avg_stmt = avg_stmt.where(VideoWatchSession.started_at >= since)
        avg_row = (await self.session.execute(avg_stmt)).one()
        avg_duration = float(avg_row[0] or 0)
        avg_percent = float(avg_row[1] or 0)

        views = await self._count_views(channel_id, since)
        likes = await self._count_reactions(channel_id, "like", since)
        comments = await self._count_comments(channel_id, since)
        engagement_rate = round((likes + comments) / views * 100, 2) if views else 0.0

        # Watch time per day
        wtpd_stmt = (
            select(
                func.date(VideoWatchSession.started_at).label("day"),
                func.coalesce(func.sum(VideoWatchSession.watched_seconds), 0).label(
                    "secs"
                ),
            )
            .join(Video, VideoWatchSession.video_id == Video.id)
            .where(Video.channel_id == channel_id)
            .group_by(literal_column("1"))
            .order_by(literal_column("1"))
        )
        if since is not None:
            wtpd_stmt = wtpd_stmt.where(VideoWatchSession.started_at >= since)
        wtpd_rows = (await self.session.execute(wtpd_stmt)).all()
        watch_time_per_day = _fill_daily([(r.day, r.secs) for r in wtpd_rows], since)

        # Avg % viewed per day
        appd_stmt = (
            select(
                func.date(VideoWatchSession.started_at).label("day"),
                func.coalesce(func.avg(VideoWatchSession.completed_percent), 0).label(
                    "pct"
                ),
            )
            .join(Video, VideoWatchSession.video_id == Video.id)
            .where(Video.channel_id == channel_id)
            .group_by(literal_column("1"))
            .order_by(literal_column("1"))
        )
        if since is not None:
            appd_stmt = appd_stmt.where(VideoWatchSession.started_at >= since)
        appd_rows = (await self.session.execute(appd_stmt)).all()
        avg_pct_per_day = _fill_daily(
            [(r.day, int(round(float(r.pct or 0) * 100))) for r in appd_rows], since
        )

        return EngagementResponse(
            period=period.value,
            total_watch_time_seconds=int(total_watch),
            average_view_duration_seconds=round(avg_duration, 1),
            average_percent_viewed=round(avg_percent * 100, 1),
            engagement_rate=engagement_rate,
            watch_time_per_day=watch_time_per_day,
            avg_percent_viewed_per_day=avg_pct_per_day,
        )

    # ---------- REAL-TIME (last 48 h) ------------------------------------

    async def get_realtime(self, channel: Channel) -> RealtimeResponse:
        channel_id = channel.id
        now = _now()
        since_48h = now - timedelta(hours=48)
        since_60m = now - timedelta(minutes=60)

        # per-hour bucket
        hour_stmt = (
            select(
                func.date_trunc("hour", VideoView.viewed_at).label("h"),
                func.count(VideoView.id).label("cnt"),
            )
            .join(Video, VideoView.video_id == Video.id)
            .where(
                Video.channel_id == channel_id,
                VideoView.viewed_at >= since_48h,
            )
            .group_by(literal_column("1"))
            .order_by(literal_column("1"))
        )
        rows = (await self.session.execute(hour_stmt)).all()
        known = {r.h.replace(microsecond=0).isoformat(): int(r.cnt) for r in rows}
        # fill 48 hourly buckets
        buckets: list[HourlyMetric] = []
        cursor = since_48h.replace(minute=0, second=0, microsecond=0)
        stop = now.replace(minute=0, second=0, microsecond=0)
        while cursor <= stop:
            key = cursor.isoformat()
            buckets.append(HourlyMetric(hour=key, count=known.get(key, 0)))
            cursor += timedelta(hours=1)

        total_48 = await self._count_views(channel_id, since_48h)
        total_60m = await self._count_views(channel_id, since_60m)

        top_stmt = (
            select(
                Video.id,
                Video.name,
                Video.thumbnail_path,
                func.count(VideoView.id).label("vc"),
                Video.likes_count,
            )
            .join(VideoView, VideoView.video_id == Video.id)
            .where(
                Video.channel_id == channel_id,
                VideoView.viewed_at >= since_48h,
            )
            .group_by(Video.id)
            .order_by(func.count(VideoView.id).desc())
            .limit(5)
        )
        top_rows = (await self.session.execute(top_stmt)).all()
        top = [
            TopVideo(
                id=r.id,
                title=r.name,
                thumbnail=r.thumbnail_path or "",
                views_count=int(r.vc or 0),
                likes_count=int(r.likes_count or 0),
                comments_count=0,
            )
            for r in top_rows
        ]

        return RealtimeResponse(
            views_last_48h=total_48,
            views_last_60min=total_60m,
            views_per_hour=buckets,
            top_videos_48h=top,
        )

    # ---------- TRAFFIC SOURCES ------------------------------------------

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

    async def get_traffic_sources(
        self, channel: Channel, period: Period = Period.LAST_28
    ) -> TrafficSourcesResponse:
        channel_id = channel.id
        since, _ = _window(period)

        stmt = (
            select(
                func.coalesce(VideoView.source_type, "unknown").label("src"),
                func.count(VideoView.id).label("cnt"),
            )
            .join(Video, VideoView.video_id == Video.id)
            .where(Video.channel_id == channel_id)
            .group_by(literal_column("1"))
            .order_by(func.count(VideoView.id).desc())
        )
        if since is not None:
            stmt = stmt.where(VideoView.viewed_at >= since)
        rows = (await self.session.execute(stmt)).all()
        return TrafficSourcesResponse(
            period=period.value,
            total_views=sum(int(r.cnt) for r in rows),
            sources=self._traffic_slices(rows),
        )

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
            .where(VideoReaction.video_id == video_id, ReactionType.name == reaction_name)
        )
        try:
            return await self._scalar_count(
                base, VideoReaction.created_at, since, until
            )
        except Exception:
            # created_at may be absent on VideoReaction in some deployments —
            # fall back to the lifetime count for this reaction on this video.
            return int((await self.session.execute(base)).scalar() or 0)

    async def _video_views_per_day(
        self, video_id: UUID, since: datetime | None
    ) -> list[DailyMetric]:
        stmt = (
            select(
                func.date(VideoView.viewed_at).label("day"),
                func.count(VideoView.id).label("cnt"),
            )
            .where(VideoView.video_id == video_id)
            .group_by(literal_column("1"))
            .order_by(literal_column("1"))
        )
        if since is not None:
            stmt = stmt.where(VideoView.viewed_at >= since)
        rows = (await self.session.execute(stmt)).all()
        return _fill_daily([(r.day, r.cnt) for r in rows], since)

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
        # completed_percent is stored as 0.0–1.0 decimal fraction
        buckets: list[RetentionBucket] = []
        for pct in (10, 25, 50, 75, 100):
            stmt = select(func.count(VideoWatchSession.id)).where(
                VideoWatchSession.video_id == video_id,
                VideoWatchSession.completed_percent >= pct / 100.0,
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
            average_percent_viewed=round(avg_percent * 100, 1),
            views_per_day=await self._video_views_per_day(video_id, since),
            retention=await self._video_retention_buckets(video_id, since),
            traffic_sources=await self._video_traffic_sources(video_id, since),
        )

    # ---------- WATCH-SESSION HEARTBEAT ----------------------------------

    async def record_watch_session(
        self, ping: WatchSessionPing, user_id: UUID | None
    ) -> WatchSessionAck:
        """
        Upsert a watch session row keyed by session_id.

        Heartbeats from the player are cumulative — we store the latest
        ``watched_seconds`` cursor and recompute ``completed_percent`` on
        every call.  First heartbeat creates the row.
        """
        completed = 0.0
        if ping.video_duration_seconds > 0:
            completed = min(
                100.0,
                round(ping.watched_seconds / ping.video_duration_seconds * 100, 2),
            )

        stmt = pg_insert(VideoWatchSession).values(
            id=ping.session_id,
            video_id=ping.video_id,
            user_id=user_id,
            watched_seconds=ping.watched_seconds,
            video_duration_seconds=ping.video_duration_seconds,
            completed_percent=completed,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[VideoWatchSession.id],
            set_={
                "watched_seconds": stmt.excluded.watched_seconds,
                "video_duration_seconds": stmt.excluded.video_duration_seconds,
                "completed_percent": stmt.excluded.completed_percent,
                "updated_at": func.now(),
            },
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return WatchSessionAck(session_id=ping.session_id, completed_percent=completed)
