import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base

if TYPE_CHECKING:
    from .user import User
    from .video import Video


class VideoView(Base):
    __tablename__ = "video_views"

    # ---- Columns ----
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Traffic source: "direct", "search", "recommendation", "external",
    # "channel_page", "playlist", "subscriptions", "unknown".
    # Nullable for backfilled historical rows.
    # Who this view belongs to, as one opaque string, so a signed-in and a
    # signed-out viewer can be deduplicated by the same unique index:
    #   "user:<uuid>"  a signed-in viewer
    #   "anon:<id>"    a signed-out viewer the browser identifies
    #   "fp:<hash>"    a signed-out viewer with no id, keyed on IP + agent
    viewer_key: Mapped[str] = mapped_column(String(80), nullable=False)
    source_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, server_default="unknown"
    )

    # ---- Relationships ----
    video: Mapped["Video"] = relationship(back_populates="views")
    user: Mapped["User | None"] = relationship(back_populates="views")

    __table_args__ = (
        Index("ix_video_views_video_id", "video_id"),
        Index("ix_video_views_user_id", "user_id"),
        Index("ix_video_views_viewed_at", "viewed_at"),
        Index("ix_video_views_source_type", "source_type"),
        Index("ix_video_views_viewer_key", "viewer_key"),
        # One row per viewer per video: views are unique viewers, not raw
        # hits. This replaced a partial unique index over (video_id,
        # user_id) that only applied WHERE user_id IS NOT NULL, so every
        # signed-out visit counted again.
        Index(
            "uq_video_views_video_viewer",
            "video_id",
            "viewer_key",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return f"<View video={self.video_id} user={self.user_id}>"

    def __str__(self) -> str:
        return f"View of {self.video_id} by {self.user_id or 'guest'}"
