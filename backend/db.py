from __future__ import annotations

from collections.abc import Generator
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def get_database_url() -> str:
    return os.getenv("DATABASE_URL") or os.getenv("TSBOT_DATABASE_URL") or "sqlite:///./tsbot.db"


def get_sqlite_db_path() -> str | None:
    database_url = get_database_url()
    sqlite_prefix = "sqlite:///"
    if not database_url.startswith(sqlite_prefix):
        return None
    return database_url.removeprefix(sqlite_prefix)


_engine = create_engine(get_database_url(), connect_args={"check_same_thread": False})
_SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def create_db_and_tables() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(_engine)
    ensure_queue_item_positions()


def ensure_queue_item_positions() -> None:
    """Add persistent queue ordering to databases created before this field."""
    inspector = inspect(_engine)
    if "queue_items" not in inspector.get_table_names():
        return

    column_names = {column["name"] for column in inspector.get_columns("queue_items")}
    if "queue_position" in column_names:
        return

    with _engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE queue_items "
                "ADD COLUMN queue_position INTEGER NOT NULL DEFAULT 0"
            )
        )
        # Existing IDs already reflect the old FIFO order.
        connection.execute(
            text("UPDATE queue_items SET queue_position = id WHERE queue_position = 0")
        )


def new_session() -> Session:
    return _SessionLocal()


def get_session() -> Generator[Session, None, None]:
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
