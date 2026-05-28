from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()


def _normalized_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://") and "+psycopg" not in database_url:
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url

normalized_database_url = _normalized_database_url(settings.database_url)
connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
engine_kwargs = {"future": True, "connect_args": connect_args}
if not settings.is_sqlite:
    engine_kwargs.update({"pool_pre_ping": True, "pool_recycle": 300})
engine = create_engine(normalized_database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
