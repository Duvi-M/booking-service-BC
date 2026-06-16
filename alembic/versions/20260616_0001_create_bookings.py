"""create bookings table

Revision ID: 20260616_0001
Revises:
Create Date: 2026-06-16 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260616_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BOOKING_STATUS_VALUES = ("pending", "confirmed", "failed", "cancelled")
BOOKING_STATUS_NAME = "booking_status"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        booking_status = postgresql.ENUM(
            *BOOKING_STATUS_VALUES,
            name=BOOKING_STATUS_NAME,
            create_type=True,
        )
        booking_status.create(bind, checkfirst=True)
        status_column_type = postgresql.ENUM(
            *BOOKING_STATUS_VALUES,
            name=BOOKING_STATUS_NAME,
            create_type=False,
        )
    else:
        status_column_type = sa.Enum(
            *BOOKING_STATUS_VALUES,
            name=BOOKING_STATUS_NAME,
            native_enum=False,
        )

    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service_type", sa.String(length=80), nullable=False),
        sa.Column("status", status_column_type, nullable=False),
        sa.Column(
            "created_at",
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bookings_status", "bookings", ["status"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("bookings")
    if bind.dialect.name == "postgresql":
        booking_status = postgresql.ENUM(
            *BOOKING_STATUS_VALUES,
            name=BOOKING_STATUS_NAME,
            create_type=True,
        )
        booking_status.drop(bind, checkfirst=True)
