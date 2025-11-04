from __future__ import annotations

from typing import Any, Iterable, Optional

from fastapi import FastAPI
from sqlmodel import SQLModel

from vention_storage.src.storage.database import get_engine, set_database_url
from vention_storage.src.storage.accessor import ModelAccessor
from vention_storage.src.storage.router_model import build_crud_router
from vention_storage.src.storage.router_database import build_db_router


def bootstrap(
    app: FastAPI,
    *,
    accessors: Iterable[ModelAccessor[Any]],
    database_url: Optional[str] = None,
    create_tables: bool = True,
    max_records_per_model: Optional[int] = 5,
    enable_db_router: bool = True,
) -> None:
    """
    Bootstrap the storage system for a FastAPI app.

    This helper wires up:
      - Database engine initialization (optionally overriding the URL).
      - Optional table creation via `SQLModel.metadata.create_all`.
      - One CRUD router per registered `ModelAccessor`.
      - The global /db router (health, audit, diagram, backup/restore) if enabled.
    """
    if database_url is not None:
        set_database_url(database_url)

    engine = get_engine()
    if create_tables:
        SQLModel.metadata.create_all(engine)

    # Per-model CRUD routers
    for accessor in accessors:
        app.include_router(
            build_crud_router(accessor, max_records=max_records_per_model)
        )

    # Global DB router (health, audit, diagram, backup/restore)
    if enable_db_router:
        app.include_router(build_db_router())
