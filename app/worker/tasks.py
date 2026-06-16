import asyncio
import random
import uuid

import structlog
from celery.exceptions import Retry
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import get_settings
from app.database import async_session_factory
from app.models import BookingStatus
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

    if external_booking_confirmation_failed():
        booking.status = BookingStatus.failed
        await session.commit()
        logger.info("booking_confirmation_failed", booking_id=str(booking.id))
        return BookingStatus.failed

    booking.status = BookingStatus.confirmed
    await session.commit()
    logger.info(
        "notification_sent",
        booking_id=str(booking.id),
        service_type=booking.service_type,
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
