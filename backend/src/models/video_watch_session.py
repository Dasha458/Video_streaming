import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base

if TYPE_CHECKING:
    from .user import User
    from .video import Video


class VideoWatchSession(Base):
    """
    Records a single playback session for watch-time / retention analytics.

    The frontend video player sends periodic heartbeats (every ~10s) while
    playback is active.  Each heartbeat upserts the row identified by
    (user_id, video_id, started_at) with the latest `watched_seconds`
    cursor.  Aggregations over this table yield YouTube-style metrics:

      * total watch time per channel / video / period
      * average view duration
      * average percentage viewed (watched / duration)
      * retention distribution
    """

    __tablename__ = "video_watch_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # total seconds the user actually watched during this session
    watched_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # video length at the time of the session (denormalised for fast retention math)
    video_duration_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # watched / duration; stored for fast avg aggregations
    completed_percent: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )

    video: Mapped["Video"] = relationship()
    user: Mapped["User | None"] = relationship()

    __table_args__ = (
        Index("ix_watch_sessions_video_id", "video_id"),
        Index("ix_watch_sessions_user_id", "user_id"),
        Index("ix_watch_sessions_started_at", "started_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<WatchSession video={self.video_id} user={self.user_id} "
            f"secs={self.watched_seconds}/{self.video_duration_seconds}>"
        )
