from datetime import UTC, datetime, timedelta

from app.models import BookingStatus
from tests.helpers import create_booking_with_status


async def test_post_bookings_creates_pending_booking(client, sample_payload):
    response = await client.post("/bookings", json=sample_payload)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == sample_payload["name"]
    assert data["service_type"] == sample_payload["service_type"]
    assert data["status"] == "pending"
    client.celery_delay_mock.assert_called_once_with(data["id"])


async def test_post_bookings_validates_required_fields(client):
    response = await client.post("/bookings", json={})

    assert response.status_code == 422


async def test_post_bookings_rejects_invalid_datetime(client, sample_payload):
    sample_payload["datetime"] = "not-a-date"

    response = await client.post("/bookings", json=sample_payload)

    assert response.status_code == 422


async def test_post_bookings_rejects_past_datetime(client, sample_payload):
    sample_payload["datetime"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()

    response = await client.post("/bookings", json=sample_payload)

    assert response.status_code == 422
    assert "datetime must be in the future" in response.text


async def test_post_bookings_rate_limit_returns_429(client, sample_payload):
    for _ in range(10):
        response = await client.post("/bookings", json=sample_payload)
        assert response.status_code == 201

    response = await client.post("/bookings", json=sample_payload)

    assert response.status_code == 429
    assert response.json()["detail"] == "Too many booking requests. Please try again later."


async def test_get_booking_returns_existing_booking(client, booking):
    response = await client.get(f"/bookings/{booking.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(booking.id)
    assert data["status"] == "pending"


async def test_get_booking_not_found_returns_404(client):
    response = await client.get("/bookings/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["detail"] == "Booking not found"


async def test_list_bookings_returns_items(client, db_session):
    await create_booking_with_status(db_session, BookingStatus.pending)
    await create_booking_with_status(db_session, BookingStatus.confirmed)

    response = await client.get("/bookings")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["limit"] == 20
    assert data["offset"] == 0


async def test_list_bookings_filters_by_status(client, db_session):
    await create_booking_with_status(db_session, BookingStatus.pending)
    await create_booking_with_status(db_session, BookingStatus.confirmed)

    response = await client.get("/bookings", params={"status": "confirmed"})

    assert response.status_code == 200
    statuses = {item["status"] for item in response.json()["items"]}
    assert statuses == {"confirmed"}


async def test_list_bookings_respects_limit_and_offset(client, db_session):
    for _ in range(3):
        await create_booking_with_status(db_session, BookingStatus.pending)

    response = await client.get("/bookings", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["limit"] == 1
    assert data["offset"] == 1


async def test_delete_booking_cancels_pending_booking(client, booking):
    response = await client.delete(f"/bookings/{booking.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


async def test_delete_booking_confirmed_returns_400(client, db_session):
    confirmed = await create_booking_with_status(db_session, BookingStatus.confirmed)

    response = await client.delete(f"/bookings/{confirmed.id}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Only pending bookings can be cancelled"


async def test_delete_booking_not_found_returns_404(client):
    response = await client.delete("/bookings/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["detail"] == "Booking not found"
