import uuid
from unittest.mock import Mock

from app.models import Booking, BookingStatus
from app.worker import tasks
from app.worker.tasks import process_booking_confirmation
from tests.helpers import create_sync_booking_with_status


def test_task_returns_none_when_booking_not_found(sync_session, monkeypatch):
    external_mock = Mock(return_value=False)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", external_mock)

    status = process_booking_confirmation(sync_session, uuid.uuid4())

    assert status is None
    external_mock.assert_not_called()


def test_successful_task_changes_pending_to_confirmed(sync_session, monkeypatch):
    booking = create_sync_booking_with_status(sync_session, BookingStatus.pending)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", Mock(return_value=False))

    status = process_booking_confirmation(sync_session, booking.id)
    refreshed = sync_session.get(Booking, booking.id)

    assert status == BookingStatus.confirmed
    assert refreshed is not None
    assert refreshed.status == BookingStatus.confirmed


def test_task_atomic_idempotency_does_not_repeat_notification(sync_session, monkeypatch):
    booking = create_sync_booking_with_status(sync_session, BookingStatus.pending)
    external_mock = Mock(return_value=False)
    logger_mock = Mock()
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", external_mock)
    monkeypatch.setattr(tasks, "logger", logger_mock)

    first_status = process_booking_confirmation(sync_session, booking.id)
    second_status = process_booking_confirmation(sync_session, booking.id)

    assert first_status == BookingStatus.confirmed
    assert second_status == BookingStatus.confirmed
    external_mock.assert_called_once()
    notification_calls = [
        call for call in logger_mock.info.call_args_list if call.args == ("notification_sent",)
    ]
    assert len(notification_calls) == 1


def test_failed_task_changes_pending_to_failed(sync_session, monkeypatch):
    booking = create_sync_booking_with_status(sync_session, BookingStatus.pending)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", Mock(return_value=True))

    status = process_booking_confirmation(sync_session, booking.id)
    refreshed = sync_session.get(Booking, booking.id)

    assert status == BookingStatus.failed
    assert refreshed is not None
    assert refreshed.status == BookingStatus.failed


def test_task_is_idempotent_when_booking_already_confirmed(sync_session, monkeypatch):
    booking = create_sync_booking_with_status(sync_session, BookingStatus.confirmed)
    external_mock = Mock(return_value=True)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", external_mock)

    status = process_booking_confirmation(sync_session, booking.id)
    refreshed = sync_session.get(Booking, booking.id)

    assert status == BookingStatus.confirmed
    assert refreshed is not None
    assert refreshed.status == BookingStatus.confirmed
    external_mock.assert_not_called()


def test_task_does_not_confirm_cancelled_booking(sync_session, monkeypatch):
    booking = create_sync_booking_with_status(sync_session, BookingStatus.cancelled)
    external_mock = Mock(return_value=False)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", external_mock)

    status = process_booking_confirmation(sync_session, booking.id)
    refreshed = sync_session.get(Booking, booking.id)

    assert status == BookingStatus.cancelled
    assert refreshed is not None
    assert refreshed.status == BookingStatus.cancelled
    external_mock.assert_not_called()
