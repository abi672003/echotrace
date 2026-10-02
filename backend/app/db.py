from collections.abc import Generator

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings


def _make_engine() -> Engine:
    settings = get_settings()
    if settings.DATABASE_URL.startswith("sqlite"):
        return create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True)


engine = _make_engine()


def create_all() -> None:
    from app import models  # noqa: F401  # import registers tables on SQLModel.metadata

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
