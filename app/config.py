from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def derive_sync_database_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg", "postgresql+psycopg", 1)


class Settings(BaseSettings):
    app_name: str = "Booking Service"
    environment: str = "local"
    database_url: str = Field(
        default="postgresql+asyncpg://booking:booking@postgres:5432/booking"
    )
    database_url_sync: str | None = None
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    rate_limit_requests: int = 10
    rate_limit_window_seconds: int = 60
    external_failure_probability: float = 0.15

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def sync_database_url(self) -> str:
        return self.database_url_sync or derive_sync_database_url(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
