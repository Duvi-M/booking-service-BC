from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fakeredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.bookings import get_redis_client
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


@pytest_asyncio.fixture
async def async_worker_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def worker_session_factory(async_worker_engine):
    return async_sessionmaker(
        bind=async_worker_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def worker_session(worker_session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with worker_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(session_factory, monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    kiq_mock = AsyncMock()
    redis_client = FakeRedis()
    monkeypatch.setattr("app.api.bookings.confirm_booking_task.kiq", kiq_mock)
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_redis_client] = lambda: redis_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        async_client.task_kiq_mock = kiq_mock
        yield async_client

    app.dependency_overrides.clear()
    redis_client.flushall()


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
