"""add notification fields

Adds is_read and notification_type columns to the notifications table.

Revision ID: b9c1d2e3f4a5
Revises: a1b2c3d4e5f6
Create Date: 2026-04-25 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b9c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column(
            "is_read",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "notifications",
        sa.Column(
            "notification_type",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"], unique=False)
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_column("notifications", "notification_type")
    op.drop_column("notifications", "is_read")
