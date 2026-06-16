"""drop single status index

Revision ID: 20260616_0003
Revises: 20260616_0002
Create Date: 2026-06-16 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260616_0003"
down_revision: str | None = "20260616_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_bookings_status", table_name="bookings")


def downgrade() -> None:
    op.create_index("ix_bookings_status", "bookings", ["status"], unique=False)
