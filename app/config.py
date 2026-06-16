from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Booking Service"
    environment: str = "local"
    database_url: str = "postgresql+asyncpg://booking:booking@postgres:5432/booking"
    redis_url: str = "redis://redis:6379/0"
    taskiq_broker_url: str | None = None
    rate_limit_requests: int = 10
    rate_limit_window_seconds: int = 60
    external_failure_probability: float = 0.15

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def background_broker_url(self) -> str:
        return self.taskiq_broker_url or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
