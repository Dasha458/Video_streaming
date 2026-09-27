"""
The channel-wide panels of Creator Studio: overview, content, audience,
engagement, real-time and traffic sources.
"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, literal_column, select, true

from src.core.status_ids import PRIVACY_PUBLIC_ID
from src.models import (
    Channel,
    Comment,
    Subscription,
    Video,
    VideoView,
    VideoWatchSession,
)
from src.schemas.analytics import (
    AudienceResponse,
    ContentResponse,
    DailyMetric,
    EngagementResponse,
    HourlyMetric,
    OverviewResponse,
    Period,
    RealtimeResponse,
    TopVideo,
    TrafficSourcesResponse,
    VideoStat,
)
from src.services.analytics._base import AnalyticsQueries
from src.services.analytics.windowing import (
    _delta,
    _now,
    _window,
)


class ChannelReports(AnalyticsQueries):
    # ---------- OVERVIEW -------------------------------------------------

    async def _overview_views_per_day(
        self, channel_id: UUID, since: datetime | None
    ) -> list[DailyMetric]:
        return await self._daily_series(
            func.count(VideoView.id),
            VideoView.viewed_at,
            since=since,
            joins=[(Video, VideoView.video_id == Video.id)],
            filters=[Video.channel_id == channel_id],
        )

    async def _overview_top_videos(
        self, channel_id: UUID, since: datetime | None, limit: int = 5
    ) -> list[TopVideo]:
        stmt = (
            select(
                Video.id,
                Video.name,
                Video.thumbnail_path,
                func.count(VideoView.id.distinct()).label("vc"),
                Video.likes_count,
                func.count(Comment.id.distinct()).label("cc"),
            )
            .outerjoin(
                VideoView,
                # The period predicate belongs in the JOIN, not the WHERE.
                # In the WHERE it discarded every row of a video whose views
                # all fell outside the window, so that video vanished from
                # the list entirely -- while a video with no views at all
                # survived through the IS NULL branch and showed a 0.
                (VideoView.video_id == Video.id)
                & ((VideoView.viewed_at >= since) if since is not None else true()),
            )
            .outerjoin(Comment, Comment.video_id == Video.id)
            .where(Video.channel_id == channel_id)
            .group_by(Video.id)
            # DISTINCT matters: joining views and comments together produces
            # one row per pair, so a plain count reported views x comments.
            # The comment count next to it was already guarded this way.
            .order_by(func.count(VideoView.id.distinct()).desc())
            .limit(limit)
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

        subscribers_per_day = await self._daily_series(
            func.count(Subscription.subscriber_id),
            Subscription.created_at,
            since=since,
            filters=[Subscription.channel_id == channel_id],
        )

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

        comments_per_day = await self._daily_series(
            func.count(Comment.id),
            Comment.created_at,
            since=since,
            joins=[(Video, Comment.video_id == Video.id)],
            filters=[Video.channel_id == channel_id],
        )

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
        watch_time_per_day = await self._daily_series(
            func.coalesce(func.sum(VideoWatchSession.watched_seconds), 0),
            VideoWatchSession.started_at,
            since=since,
            joins=[(Video, VideoWatchSession.video_id == Video.id)],
            filters=[Video.channel_id == channel_id],
        )

        # Avg % viewed per day
        avg_pct_per_day = await self._daily_series(
            func.coalesce(func.avg(VideoWatchSession.completed_percent), 0),
            VideoWatchSession.started_at,
            since=since,
            joins=[(Video, VideoWatchSession.video_id == Video.id)],
            filters=[Video.channel_id == channel_id],
            transform=lambda v: int(round(float(v or 0))),
        )

        return EngagementResponse(
            period=period.value,
            total_watch_time_seconds=int(total_watch),
            average_view_duration_seconds=round(avg_duration, 1),
            # completed_percent is stored as 0-100 by record_watch_session;
            # this used to multiply by 100 again, so a fully watched video
            # reported 10000 %.
            average_percent_viewed=round(avg_percent, 1),
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
