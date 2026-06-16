import time
import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from redis import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import Settings, get_settings
from app.database import get_session
from app.models import BookingStatus
from app.schemas import BookingCreate, BookingList, BookingRead
from app.worker.tasks import confirm_booking_task

router = APIRouter(prefix="/bookings", tags=["bookings"])

RATE_LIMIT_MESSAGE = "Too many booking requests. Please try again later."


@lru_cache
def build_redis_client(redis_url: str) -> Redis:
    return Redis.from_url(redis_url)


def get_redis_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Redis:
    return build_redis_client(settings.redis_url)


def rate_limit(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    redis_client: Annotated[Redis, Depends(get_redis_client)],
) -> None:
    client = request.client.host if request.client else "unknown"
    window = int(time.time() // settings.rate_limit_window_seconds)
    key = f"rate_limit:bookings:{client}:{window}"
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, settings.rate_limit_window_seconds)

    if count > settings.rate_limit_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=RATE_LIMIT_MESSAGE,
        )


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
    await confirm_booking_task.kiq(str(booking.id))
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
