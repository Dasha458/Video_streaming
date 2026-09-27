"""
Creator analytics: the entry point the API talks to.

Provides YouTube-Studio-style aggregations over a channel's content:
  * overview, content, audience
  * engagement (watch-time, retention, engagement rate)
  * real-time (last 48 h, last 60 min)
  * traffic sources (breakdown by ``VideoView.source_type``)
  * per-video deep-dive
  * watch-session heartbeat upsert

All period-aware queries accept a :class:`~src.schemas.analytics.Period`
value ("7d" / "28d" / "90d" / "365d" / "all"). Delta metrics compare the
current window with the immediately preceding one of equal size (for
"all", the previous window is considered empty).

This class used to hold all of the above -- twenty-six methods and seven
unrelated report surfaces plus the one write path, in a single file. The
work now lives in ``channel_reports``, ``video_reports`` and ``sessions``,
which share their SQL plumbing through ``_base.AnalyticsQueries``; what
remains here is the facade the routers depend on, so no caller had to
change and each report can be read, tested and altered on its own.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Channel
from src.schemas.analytics import (
    AudienceResponse,
    ContentResponse,
    EngagementResponse,
    OverviewResponse,
    Period,
    RealtimeResponse,
    TrafficSourcesResponse,
    VideoAnalyticsResponse,
    WatchSessionAck,
    WatchSessionPing,
)
from src.services.analytics.channel_reports import ChannelReports
from src.services.analytics.sessions import WatchSessions
from src.services.analytics.video_reports import VideoReports


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._channel = ChannelReports(session)
        self._video = VideoReports(session)
        self._sessions = WatchSessions(session)

    # ---------- channel lookup -------------------------------------------

    async def get_channel(self, user_id: UUID) -> Channel | None:
        return await self._channel.get_channel(user_id)

    # ---------- channel-wide reports --------------------------------------

    async def get_overview(
        self, channel: Channel, period: Period = Period.LAST_28
    ) -> OverviewResponse:
        return await self._channel.get_overview(channel, period)

    async def get_content(
        self, channel: Channel, period: Period = Period.LAST_28
    ) -> ContentResponse:
        return await self._channel.get_content(channel, period)

    async def get_audience(
        self, channel: Channel, period: Period = Period.LAST_28
    ) -> AudienceResponse:
        return await self._channel.get_audience(channel, period)

    async def get_engagement(
        self, channel: Channel, period: Period = Period.LAST_28
    ) -> EngagementResponse:
        return await self._channel.get_engagement(channel, period)

    async def get_realtime(self, channel: Channel) -> RealtimeResponse:
        return await self._channel.get_realtime(channel)

    async def get_traffic_sources(
        self, channel: Channel, period: Period = Period.LAST_28
    ) -> TrafficSourcesResponse:
        return await self._channel.get_traffic_sources(channel, period)

    # ---------- per-video deep dive ---------------------------------------

    async def get_video_analytics(
        self,
        channel: Channel,
        video_id: UUID,
        period: Period = Period.LAST_28,
    ) -> VideoAnalyticsResponse | None:
        return await self._video.get_video_analytics(channel, video_id, period)

    # ---------- watch-session heartbeat -----------------------------------

    async def record_watch_session(
        self, ping: WatchSessionPing, user_id: UUID | None
    ) -> WatchSessionAck:
        return await self._sessions.record_watch_session(ping, user_id)
