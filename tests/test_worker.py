import uuid
from unittest.mock import Mock

from sqlalchemy import func, update

from app.models import Booking, BookingStatus
from app.worker import tasks
from app.worker.tasks import process_booking_confirmation
from tests.helpers import create_booking_with_status


async def test_task_returns_none_when_booking_not_found(worker_session, monkeypatch):
    external_mock = Mock(return_value=False)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", external_mock)

    status = await process_booking_confirmation(worker_session, uuid.uuid4())

    assert status is None
    external_mock.assert_not_called()


async def test_successful_task_changes_pending_to_confirmed(worker_session, monkeypatch):
    booking = await create_booking_with_status(worker_session, BookingStatus.pending)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", Mock(return_value=False))

    status = await process_booking_confirmation(worker_session, booking.id)
    refreshed = await worker_session.get(Booking, booking.id)

    assert status == BookingStatus.confirmed
    assert refreshed is not None
    assert refreshed.status == BookingStatus.confirmed


async def test_task_atomic_idempotency_does_not_repeat_notification(
    worker_session,
    monkeypatch,
):
    booking = await create_booking_with_status(worker_session, BookingStatus.pending)
    external_mock = Mock(return_value=False)
    logger_mock = Mock()
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", external_mock)
    monkeypatch.setattr(tasks, "logger", logger_mock)

    first_status = await process_booking_confirmation(worker_session, booking.id)
    second_status = await process_booking_confirmation(worker_session, booking.id)

    assert first_status == BookingStatus.confirmed
    assert second_status == BookingStatus.confirmed
    external_mock.assert_called_once()
    notification_calls = [
        call for call in logger_mock.info.call_args_list if call.args == ("notification_sent",)
    ]
    assert len(notification_calls) == 1


async def test_task_atomic_update_loses_race_does_not_duplicate_notification(
    worker_session,
    worker_session_factory,
    monkeypatch,
):
    booking = await create_booking_with_status(worker_session, BookingStatus.pending)
    external_mock = Mock(return_value=False)
    logger_mock = Mock()
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", external_mock)
    monkeypatch.setattr(tasks, "logger", logger_mock)

    async with worker_session_factory() as session_a, worker_session_factory() as session_b:
        stale_booking = await session_b.get(Booking, booking.id)
        assert stale_booking.status == BookingStatus.pending
        update_results = []
        original_execute = session_b.execute

        async def execute_spy(*args, **kwargs):
            result = await original_execute(*args, **kwargs)

            class ResultProxy:
                def __getattr__(self, name):
                    return getattr(result, name)

                def one_or_none(self):
                    value = result.one_or_none()
                    update_results.append(value)
                    return value

            return ResultProxy()

        session_b.execute = execute_spy
        statement = (
            update(Booking)
            .where(
                Booking.id == booking.id,
                Booking.status == BookingStatus.pending,
            )
            .values(status=BookingStatus.confirmed, updated_at=func.now())
            .returning(Booking.id)
        )
        result = await session_a.execute(statement)
        assert result.one_or_none() is not None
        await session_a.commit()

        status = await process_booking_confirmation(session_b, booking.id)

    assert status == BookingStatus.confirmed
    assert update_results == [None]
    external_mock.assert_called_once()
    notification_calls = [
        call
        for call in logger_mock.info.call_args_list
        if call.args == ("notification_sent",)
        and call.kwargs.get("booking_id") == str(booking.id)
    ]
    assert notification_calls == []


async def test_failed_task_changes_pending_to_failed(worker_session, monkeypatch):
    booking = await create_booking_with_status(worker_session, BookingStatus.pending)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", Mock(return_value=True))

    status = await process_booking_confirmation(worker_session, booking.id)
    refreshed = await worker_session.get(Booking, booking.id)

    assert status == BookingStatus.failed
    assert refreshed is not None
    assert refreshed.status == BookingStatus.failed


async def test_task_is_idempotent_when_booking_already_confirmed(worker_session, monkeypatch):
    booking = await create_booking_with_status(worker_session, BookingStatus.confirmed)
    external_mock = Mock(return_value=True)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", external_mock)

    status = await process_booking_confirmation(worker_session, booking.id)
    refreshed = await worker_session.get(Booking, booking.id)

    assert status == BookingStatus.confirmed
    assert refreshed is not None
    assert refreshed.status == BookingStatus.confirmed
    external_mock.assert_not_called()


async def test_task_does_not_confirm_cancelled_booking(worker_session, monkeypatch):
    booking = await create_booking_with_status(worker_session, BookingStatus.cancelled)
    external_mock = Mock(return_value=False)
    monkeypatch.setattr(tasks, "external_booking_confirmation_failed", external_mock)

    status = await process_booking_confirmation(worker_session, booking.id)
    refreshed = await worker_session.get(Booking, booking.id)

    assert status == BookingStatus.cancelled
    assert refreshed is not None
    assert refreshed.status == BookingStatus.cancelled
    external_mock.assert_not_called()
