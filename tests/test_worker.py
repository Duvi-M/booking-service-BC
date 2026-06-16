import uuid
from unittest.mock import Mock

from app import crud
from app.models import BookingStatus
from app.worker import tasks
from app.worker.tasks import process_booking_confirmation
from tests.helpers import create_booking_with_status


async def test_task_returns_none_when_booking_not_found(db_session, monkeypatch):
    external_mock = Mock(return_value=False)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", external_mock)

    status = await process_booking_confirmation(db_session, uuid.uuid4())

    assert status is None
    external_mock.assert_not_called()


async def test_successful_task_changes_pending_to_confirmed(db_session, monkeypatch):
    booking = await create_booking_with_status(db_session, BookingStatus.pending)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", Mock(return_value=False))

    status = await process_booking_confirmation(db_session, booking.id)
    refreshed = await crud.get_booking(db_session, booking.id)

    assert status == BookingStatus.confirmed
    assert refreshed is not None
    assert refreshed.status == BookingStatus.confirmed


async def test_failed_task_changes_pending_to_failed(db_session, monkeypatch):
    booking = await create_booking_with_status(db_session, BookingStatus.pending)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", Mock(return_value=True))

    status = await process_booking_confirmation(db_session, booking.id)
    refreshed = await crud.get_booking(db_session, booking.id)

    assert status == BookingStatus.failed
    assert refreshed is not None
    assert refreshed.status == BookingStatus.failed


async def test_task_is_idempotent_when_booking_already_confirmed(db_session, monkeypatch):
    booking = await create_booking_with_status(db_session, BookingStatus.confirmed)
    external_mock = Mock(return_value=True)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", external_mock)

    status = await process_booking_confirmation(db_session, booking.id)
    refreshed = await crud.get_booking(db_session, booking.id)

    assert status == BookingStatus.confirmed
    assert refreshed is not None
    assert refreshed.status == BookingStatus.confirmed
    external_mock.assert_not_called()


async def test_task_does_not_confirm_cancelled_booking(db_session, monkeypatch):
    booking = await create_booking_with_status(db_session, BookingStatus.cancelled)
    external_mock = Mock(return_value=False)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", external_mock)

    status = await process_booking_confirmation(db_session, booking.id)
    refreshed = await crud.get_booking(db_session, booking.id)

    assert status == BookingStatus.cancelled
    assert refreshed is not None
    assert refreshed.status == BookingStatus.cancelled
    external_mock.assert_not_called()
