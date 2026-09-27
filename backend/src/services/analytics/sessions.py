"""
The one write path in analytics: the player's watch-session heartbeat.

Kept apart from the report modules because it is the only thing here that
changes data rather than reading it.
"""

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.models import (
    VideoWatchSession,
)
from src.schemas.analytics import (
    WatchSessionAck,
    WatchSessionPing,
)
from src.services.analytics._base import AnalyticsQueries


class WatchSessions(AnalyticsQueries):
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
