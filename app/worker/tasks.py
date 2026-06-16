import random
import uuid

import structlog
from celery.exceptions import Retry
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Booking, BookingStatus
from app.worker.celery_app import celery_app
from app.worker.db import sync_session_factory

logger = structlog.get_logger(__name__)


def external_booking_confirmation_failed() -> bool:
    settings = get_settings()
    return random.random() < settings.external_failure_probability


def process_booking_confirmation(
    session: Session,
    booking_id: uuid.UUID,
) -> BookingStatus | None:
    booking = session.get(Booking, booking_id)
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
    result = session.execute(statement)
    updated_booking = result.one_or_none()

    if updated_booking is None:
        session.rollback()
        booking = session.get(Booking, booking_id)
        return booking.status if booking else None

    session.commit()

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


def _confirm_booking(booking_id: str) -> str | None:
    parsed_booking_id = uuid.UUID(booking_id)
    with sync_session_factory() as session:
        status = process_booking_confirmation(session, parsed_booking_id)
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
        return _confirm_booking(booking_id)
    except Retry:
        raise
