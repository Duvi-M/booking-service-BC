import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus
from app.schemas import BookingCreate


async def create_booking(session: AsyncSession, payload: BookingCreate) -> Booking:
    booking = Booking(
        name=payload.name,
        datetime=payload.datetime,
        service_type=payload.service_type,
        status=BookingStatus.pending,
    )
    session.add(booking)
    await session.commit()
    await session.refresh(booking)
    return booking


async def get_booking(session: AsyncSession, booking_id: uuid.UUID) -> Booking | None:
    return await session.get(Booking, booking_id)


async def list_bookings(
    session: AsyncSession,
    *,
    status: BookingStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Booking]:
    statement = select(Booking).order_by(Booking.created_at.desc()).limit(limit).offset(offset)
    if status is not None:
        statement = statement.where(Booking.status == status)
    result = await session.scalars(statement)
    return list(result.all())


async def cancel_booking(session: AsyncSession, booking: Booking) -> Booking:
    booking.status = BookingStatus.cancelled
    await session.commit()
    await session.refresh(booking)
    return booking
