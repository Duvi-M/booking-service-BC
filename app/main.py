from fastapi import FastAPI

from app.api.bookings import router as bookings_router
from app.logging_config import configure_logging

configure_logging()

app = FastAPI(
    title="Booking Service",
    version="1.0.0",
    description="Small async backend for appointment bookings.",
)

app.include_router(bookings_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
