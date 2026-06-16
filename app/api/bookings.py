import time
import uuid
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import Settings, get_settings
from app.database import get_session
from app.models import BookingStatus
from app.schemas import BookingCreate, BookingList, BookingRead
from app.worker.tasks import confirm_booking_task

router = APIRouter(prefix="/bookings", tags=["bookings"])

RateBucket = dict[str, deque[float]]
_rate_buckets: RateBucket = defaultdict(deque)


def rate_limit(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = _rate_buckets[client]

    while bucket and now - bucket[0] > settings.rate_limit_window_seconds:
        bucket.popleft()

    if len(bucket) >= settings.rate_limit_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many booking requests. Please try again later.",
        )

    bucket.append(now)


@router.post(
    "",
    response_model=BookingRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit)],
)
async def create_booking(
    payload: BookingCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BookingRead:
    booking = await crud.create_booking(session, payload)
    confirm_booking_task.delay(str(booking.id))
    return BookingRead.model_validate(booking)


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BookingRead:
    booking = await crud.get_booking(session, booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return BookingRead.model_validate(booking)


@router.get("", response_model=BookingList)
async def list_bookings(
    session: Annotated[AsyncSession, Depends(get_session)],
    status_filter: Annotated[BookingStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BookingList:
    bookings = await crud.list_bookings(
        session,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return BookingList(
        items=[BookingRead.model_validate(booking) for booking in bookings],
        limit=limit,
        offset=offset,
    )


@router.delete("/{booking_id}", response_model=BookingRead)
async def delete_booking(
    booking_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BookingRead:
    booking = await crud.get_booking(session, booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    if booking.status != BookingStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending bookings can be cancelled",
        )
    booking = await crud.cancel_booking(session, booking)
    return BookingRead.model_validate(booking)
