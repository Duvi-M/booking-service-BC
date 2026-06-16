"""add status created_at index

Revision ID: 20260616_0002
Revises: 20260616_0001
Create Date: 2026-06-16 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260616_0002"
down_revision: str | None = "20260616_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_bookings_status_created_at",
        "bookings",
        ["status", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bookings_status_created_at", table_name="bookings")
