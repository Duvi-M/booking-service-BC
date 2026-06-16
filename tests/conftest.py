from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.bookings import _rate_buckets
from app.database import Base, get_session
from app.main import app
from app.models import Booking, BookingStatus


@pytest.fixture
def sample_payload() -> dict[str, str]:
    return {
        "name": "Ada Lovelace",
        "datetime": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "service_type": "consultation",
    }


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def sync_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with factory() as session:
        yield session

    engine.dispose()


@pytest_asyncio.fixture
async def client(session_factory, monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    delay_mock = MagicMock()
    monkeypatch.setattr("app.api.bookings.confirm_booking_task.delay", delay_mock)
    _rate_buckets.clear()
    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        async_client.celery_delay_mock = delay_mock
        yield async_client

    app.dependency_overrides.clear()
    _rate_buckets.clear()


@pytest_asyncio.fixture
async def booking(db_session: AsyncSession) -> Booking:
    item = Booking(
        name="Grace Hopper",
        datetime=datetime.now(UTC) + timedelta(days=2),
        service_type="diagnostics",
        status=BookingStatus.pending,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item
