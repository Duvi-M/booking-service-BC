import asyncio
import random
import uuid

import structlog
from celery.exceptions import Retry
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import get_settings
from app.database import async_session_factory
from app.models import Booking, BookingStatus
from app.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


def external_booking_confirmation_failed() -> bool:
    settings = get_settings()
    return random.random() < settings.external_failure_probability


async def process_booking_confirmation(
    session: AsyncSession,
    booking_id: uuid.UUID,
) -> BookingStatus | None:
    booking = await crud.get_booking(session, booking_id)
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
        booking = await crud.get_booking(session, booking_id)
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


async def _confirm_booking_async(booking_id: str) -> str | None:
    parsed_booking_id = uuid.UUID(booking_id)
    async with async_session_factory() as session:
        status = await process_booking_confirmation(session, parsed_booking_id)
        return status.value if status else None


@celery_app.task(
    bind=True,
    name="bookings.confirm_booking",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=30,
    retry_jitter=True,
    max_retries=3,
)
def confirm_booking_task(self, booking_id: str) -> str | None:
    try:
        return asyncio.run(_confirm_booking_async(booking_id))
    except Retry:
        raise
