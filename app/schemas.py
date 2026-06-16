import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import BookingStatus


class BookingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    datetime: datetime
    service_type: str = Field(min_length=1, max_length=80)

    @field_validator("datetime")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must include timezone information")
        if value <= datetime.now(UTC):
            raise ValueError("datetime must be in the future")
        return value


class BookingRead(BaseModel):
    id: uuid.UUID
    name: str
    datetime: datetime
    service_type: str
    status: BookingStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookingList(BaseModel):
    items: list[BookingRead]
    limit: int
    offset: int
