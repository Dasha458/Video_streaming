"""creator analytics extensions

Adds YouTube-style creator analytics support:
  * new ``video_watch_sessions`` table for watch-time / retention metrics
  * ``source_type`` column on ``video_views`` for traffic-source breakdown
  * supporting indexes on viewed_at / source_type for fast period queries

Revision ID: a1b2c3d4e5f6
Revises: 0cd1eae79045
Create Date: 2026-04-21 10:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "0cd1eae79045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- video_views: add source_type + indexes ----------------------------
    op.add_column(
        "video_views",
        sa.Column(
            "source_type",
            sa.String(length=32),
            nullable=True,
            server_default="unknown",
        ),
    )
    op.create_index(
        "ix_video_views_viewed_at", "video_views", ["viewed_at"], unique=False
    )
    op.create_index(
        "ix_video_views_source_type",
        "video_views",
        ["source_type"],
        unique=False,
    )

    # --- video_watch_sessions ---------------------------------------------
    op.create_table(
        "video_watch_sessions",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "video_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "watched_seconds",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "video_duration_seconds",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "completed_percent",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        "ix_watch_sessions_video_id",
        "video_watch_sessions",
        ["video_id"],
        unique=False,
    )
    op.create_index(
        "ix_watch_sessions_user_id",
        "video_watch_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_watch_sessions_started_at",
        "video_watch_sessions",
        ["started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_watch_sessions_started_at", table_name="video_watch_sessions")
    op.drop_index("ix_watch_sessions_user_id", table_name="video_watch_sessions")
    op.drop_index("ix_watch_sessions_video_id", table_name="video_watch_sessions")
    op.drop_table("video_watch_sessions")

    op.drop_index("ix_video_views_source_type", table_name="video_views")
    op.drop_index("ix_video_views_viewed_at", table_name="video_views")
    op.drop_column("video_views", "source_type")
