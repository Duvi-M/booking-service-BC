from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.bookings import router as bookings_router
from app.logging_config import configure_logging
from app.worker.broker import broker

configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    await broker.startup()
    try:
        yield
    finally:
        await broker.shutdown()


app = FastAPI(
    title="Booking Service",
    version="1.0.0",
    description="Small async backend for appointment bookings.",
    lifespan=lifespan,
)

app.include_router(bookings_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
