from __future__ import annotations

from typing import Optional
from sqlmodel import SQLModel

from vention_storage.src.storage.database import get_engine, set_database_url


__all__ = ["bootstrap"]


# ---------------------------------------------------------
# Database setup
# ---------------------------------------------------------


def bootstrap(
    *,
    database_url: Optional[str] = None,
    create_tables: bool = True,
) -> None:
    """
    Initialize the database engine and optionally create tables.

    This function performs **environment setup only**:
      - Applies a database URL override (if provided)
      - Creates SQLModel tables (if requested)

    It does **not** register any FastAPI routers or RPC bundles.

    Example:
        >>> from storage.bootstrap import bootstrap
        >>> bootstrap(database_url="sqlite:///mydb.sqlite")

    Args:
        database_url: Optional DB URL override (e.g. sqlite:///foo.sqlite)
        create_tables: Whether to auto-create tables using metadata.
    """
    if database_url is not None:
        set_database_url(database_url)

    engine = get_engine()

    if create_tables:
        SQLModel.metadata.create_all(engine)
