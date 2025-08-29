from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

__all__ = [
    "set_database_url",
    "get_engine",
    "transaction",
    "use_session",
    "CURRENT_SESSION",
]

_DATABASE_URL = os.getenv("VENTION_STORAGE_DATABASE_URL", "sqlite:///./storage.db")
_ENGINE: Optional[Engine] = None
CURRENT_SESSION: ContextVar[Optional[Session]] = ContextVar(
    "VENTION_STORAGE_CURRENT_SESSION", default=None
)


def set_database_url(url: str) -> None:
    """
    Configure the database URL before the engine is created.
    Raise if the engine was already initialized.
    """
    global _DATABASE_URL, _ENGINE
    if _ENGINE is not None:
        raise RuntimeError(
            "Database engine already initialized. Call set_database_url() before first use."
        )
    _DATABASE_URL = url


def _attach_sqlite_pragmas(engine: Engine) -> None:
    """
    In SQLite foreign key enforcement is disabled by default.
    Without it, insertions of invalid foreign keys will succeed.
    """

    def _set_sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    event.listen(engine, "connect", _set_sqlite_pragmas)


def get_engine() -> Engine:
    """Return a singleton SQLAlchemy engine (created on first use)."""
    global _ENGINE
    if _ENGINE is None:
        connect_args = (
            {"check_same_thread": False} if _DATABASE_URL.startswith("sqlite") else {}
        )
        _ENGINE = create_engine(_DATABASE_URL, echo=False, connect_args=connect_args)
        _attach_sqlite_pragmas(_ENGINE)
    return _ENGINE


@contextmanager
def transaction() -> Iterator[Session]:
    """
    Yield a Session wrapped in a single atomic transaction.
    Commits on success; rolls back on error.
    Use this when you have multiple all-or-nothing operations.

    Also sets CURRENT_SESSION for the duration, so accessors/hooks can reuse it.
    """
    engine = get_engine()
    with Session(engine, expire_on_commit=False) as session:
        token = CURRENT_SESSION.set(session)
        try:
            with session.begin():
                yield session
        finally:
            CURRENT_SESSION.reset(token)


@contextmanager
def use_session(session: Optional[Session] = None) -> Iterator[Session]:
    """
    This helper lets accessors and hooks run DB work without duplicating
    session-management code. It does not open a transaction by itself;
    for atomic multi-write operations prefer `transaction()`.
    """
    if session is not None:
        token = CURRENT_SESSION.set(session)
        try:
            yield session
        finally:
            CURRENT_SESSION.reset(token)
        return

    with Session(get_engine(), expire_on_commit=False) as s:
        token = CURRENT_SESSION.set(s)
        try:
            yield s
        finally:
            CURRENT_SESSION.reset(token)
