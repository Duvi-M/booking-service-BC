import asyncio
import random
import uuid

import structlog
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_factory
from app.models import Booking, BookingStatus
from app.worker.broker import broker

logger = structlog.get_logger(__name__)
MAX_TASK_ATTEMPTS = 3
BASE_RETRY_DELAY_SECONDS = 1.0
MAX_RETRY_DELAY_SECONDS = 8.0


def external_booking_confirmation_failed() -> bool:
    settings = get_settings()
    return random.random() < settings.external_failure_probability


async def process_booking_confirmation(
    session: AsyncSession,
    booking_id: uuid.UUID,
) -> BookingStatus | None:
    booking = await session.get(Booking, booking_id)
    if booking is None:
        logger.info("booking_task_skipped", booking_id=str(booking_id), reason="not_found")
        return None

    if booking.status != BookingStatus.pending:
        logger.info(
            "booking_task_skipped",
            booking_id=str(booking_id),
            status=booking.status.value,
            reason="not_pending",
        )
        return booking.status

    new_status = (
        BookingStatus.failed
        if external_booking_confirmation_failed()
        else BookingStatus.confirmed
    )
    statement = (
        update(Booking)
        .where(
            Booking.id == booking_id,
            Booking.status == BookingStatus.pending,
        )
        .values(status=new_status, updated_at=func.now())
        .returning(Booking.id, Booking.service_type)
    )
    result = await session.execute(statement)
    updated_booking = result.one_or_none()

    if updated_booking is None:
        await session.rollback()
        booking = await session.get(Booking, booking_id)
        if booking is not None:
            await session.refresh(booking)
        return booking.status if booking else None

    await session.commit()

    if new_status == BookingStatus.failed:
        logger.info("booking_confirmation_failed", booking_id=str(booking.id))
        return BookingStatus.failed

    logger.info(
        "notification_sent",
        booking_id=str(updated_booking.id),
        service_type=updated_booking.service_type,
        status=BookingStatus.confirmed.value,
    )
    return BookingStatus.confirmed


async def _confirm_booking(booking_id: str) -> str | None:
    parsed_booking_id = uuid.UUID(booking_id)
    async with async_session_factory() as session:
        status = await process_booking_confirmation(session, parsed_booking_id)
        return status.value if status else None


def retry_delay(attempt: int) -> float:
    delay = min(BASE_RETRY_DELAY_SECONDS * (2 ** (attempt - 1)), MAX_RETRY_DELAY_SECONDS)
    return delay + random.uniform(0, 0.25)


@broker.task(task_name="bookings.confirm_booking")
async def confirm_booking_task(booking_id: str) -> str | None:
    for attempt in range(1, MAX_TASK_ATTEMPTS + 1):
        try:
            return await _confirm_booking(booking_id)
        except Exception:
            if attempt >= MAX_TASK_ATTEMPTS:
                logger.exception(
                    "booking_task_retry_exhausted",
                    booking_id=booking_id,
                    attempts=attempt,
                )
                raise
            delay = retry_delay(attempt)
            logger.warning(
                "booking_task_retry_scheduled",
                booking_id=booking_id,
                attempt=attempt,
                delay_seconds=delay,
            )
            await asyncio.sleep(delay)

    return None
