from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus


async def create_booking_with_status(
    session: AsyncSession,
    status: BookingStatus,
) -> Booking:
    item = Booking(
        name=f"{status.value.title()} Booking",
        datetime=datetime.now(UTC) + timedelta(days=3),
        service_type="therapy",
        status=status,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


def create_sync_booking_with_status(
    session: Session,
    status: BookingStatus,
) -> Booking:
    item = Booking(
        name=f"{status.value.title()} Booking",
        datetime=datetime.now(UTC) + timedelta(days=3),
        service_type="therapy",
        status=status,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
