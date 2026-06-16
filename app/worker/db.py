from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def build_sync_engine(database_url: str | None = None):
    settings = get_settings()
    return create_engine(
        database_url or settings.sync_database_url,
        pool_pre_ping=True,
    )


sync_engine = build_sync_engine()
sync_session_factory = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
)


def get_sync_session() -> Generator[Session, None, None]:
    with sync_session_factory() as session:
        yield session
