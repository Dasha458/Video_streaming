"""video views are one row per viewer, signed in or not

Views were counted once per (video, user) and only for signed-in people:
the unique index was partial, WHERE user_id IS NOT NULL, so every
signed-out visit could insert again. Counting both kinds together made
"views" mean neither unique viewers nor raw hits, which is why an
engagement rate could come out above 100 %.

Each row now carries a viewer_key -- "user:<uuid>", "anon:<id>" or a
hash of address and user agent -- and the unique index covers
(video_id, viewer_key). A view is one viewer, whoever they are.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-09-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "video_views",
        sa.Column("viewer_key", sa.String(length=80), nullable=True),
    )

    # Signed-in rows already had an identity. Signed-out ones never did, so
    # each keeps its own key: they cannot be merged after the fact without
    # inventing which of them were the same person.
    op.execute(
        """
        UPDATE video_views
           SET viewer_key = CASE
                 WHEN user_id IS NOT NULL THEN 'user:' || user_id::text
                 ELSE 'legacy:' || id::text
               END
         WHERE viewer_key IS NULL
        """
    )

    op.alter_column("video_views", "viewer_key", nullable=False)

    op.drop_index("uq_video_views_video_user", table_name="video_views")
    op.create_index(
        "ix_video_views_viewer_key", "video_views", ["viewer_key"], unique=False
    )
    op.create_index(
        "uq_video_views_video_viewer",
        "video_views",
        ["video_id", "viewer_key"],
        unique=True,
    )

    # views_count was incremented per inserted row, so it already matches
    # the number of rows; realign it anyway, since rows could have been
    # inserted while an earlier version double-counted.
    op.execute(
        """
        UPDATE videos v
           SET views_count = c.n
          FROM (
                SELECT video_id, count(*) AS n
                  FROM video_views
              GROUP BY video_id
               ) AS c
         WHERE c.video_id = v.id
           AND v.views_count IS DISTINCT FROM c.n
        """
    )


def downgrade() -> None:
    op.drop_index("uq_video_views_video_viewer", table_name="video_views")
    op.drop_index("ix_video_views_viewer_key", table_name="video_views")
    op.create_index(
        "uq_video_views_video_user",
        "video_views",
        ["video_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.drop_column("video_views", "viewer_key")
