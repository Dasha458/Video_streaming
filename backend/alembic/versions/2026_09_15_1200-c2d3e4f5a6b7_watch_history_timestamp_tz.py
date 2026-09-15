"""watch_history last_watched_at gets a timezone

Every other timestamp column in the schema is TIMESTAMP WITH TIME ZONE;
watch_history.last_watched_at was the one holdout still declared as a naive
TIMESTAMP, so app code writing timezone-aware UTC datetimes into it (as it
does everywhere else) failed at the driver level.

Revision ID: c2d3e4f5a6b7
Revises: b9c1d2e3f4a5
Create Date: 2026-09-15 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b9c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "watch_history",
        "last_watched_at",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(timezone=False),
        postgresql_using="last_watched_at AT TIME ZONE 'UTC'",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "watch_history",
        "last_watched_at",
        type_=sa.DateTime(timezone=False),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using="last_watched_at AT TIME ZONE 'UTC'",
        existing_nullable=False,
    )
