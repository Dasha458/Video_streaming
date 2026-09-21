"""seed lookup tables

The application addresses its lookup rows by deterministic ids --
uuid5(NAMESPACE_DNS, "<scope>:<name>") (see src/core/status_ids.py and the
category/reaction lookups in the services) -- but nothing created those rows
except the optional demo seeder in utils/db_seeder.py. On a fresh database
`alembic upgrade head` left video_statuses, privacy_statuses, reaction_types
and categories empty, so the first upload failed on a foreign key.

Reference data the code depends on belongs to the schema, so it is seeded
here, idempotently. The demo seeder keeps inserting the same ids with
ON CONFLICT DO NOTHING, so both paths agree.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-09-21 12:00:00.000000
"""

from typing import Sequence, Union
from uuid import NAMESPACE_DNS, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, insert

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _id(scope: str, name: str):
    return uuid5(NAMESPACE_DNS, f"{scope}:{name.lower()}")


VIDEO_STATUSES = ["queued", "processing", "ready", "failed"]
PRIVACY_STATUSES = ["public", "private"]
REACTION_TYPES = [("like", "/icons/like.png"), ("dislike", "/icons/dislike.png")]
USER_STATUSES = ["active", "banned", "deleted"]
ROLES = [
    ("admin", "Administrator role"),
    ("user", "View, comment, react, create videos"),
]
# Must match VideoCategory in src/schemas/video.py.
CATEGORIES = [
    "education", "entertainment", "music", "gaming", "technology", "science",
    "movies", "sports", "news", "travel", "lifestyle", "fashion",
    "health & fitness", "food & cooking", "comedy", "documentary",
    "art & design", "business & finance", "animals & nature", "automotive",
    "history", "podcasts", "shorts",
]  # fmt: skip


def _table(name: str, *cols: str) -> sa.Table:
    return sa.table(
        name,
        sa.column("id", UUID(as_uuid=True)),
        *(sa.column(c, sa.String) for c in cols),
    )


def _seed(table: sa.Table, rows: list[dict]) -> None:
    op.execute(insert(table).values(rows).on_conflict_do_nothing(index_elements=["id"]))


def upgrade() -> None:
    _seed(
        _table("video_statuses", "value"),
        [{"id": _id("video_status", v), "value": v} for v in VIDEO_STATUSES],
    )
    _seed(
        _table("privacy_statuses", "name"),
        [{"id": _id("privacy_status", n), "name": n} for n in PRIVACY_STATUSES],
    )
    _seed(
        _table("reaction_types", "name", "path"),
        [
            {"id": _id("reaction_type", n), "name": n, "path": p}
            for n, p in REACTION_TYPES
        ],
    )
    _seed(
        _table("categories", "name"),
        [{"id": _id("video_category", n), "name": n} for n in CATEGORIES],
    )
    _seed(
        _table("user_statuses", "value"),
        [{"id": _id("user_status", v), "value": v} for v in USER_STATUSES],
    )
    _seed(
        _table("roles", "name", "description"),
        [{"id": _id("user_role", n), "name": n, "description": d} for n, d in ROLES],
    )


def downgrade() -> None:
    # Reference rows are left in place: removing them would orphan every
    # video/user that points at them, and they are harmless if unused.
    pass
