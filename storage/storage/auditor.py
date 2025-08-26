from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Column
from sqlalchemy.dialects.sqlite import JSON
from sqlmodel import Field, SQLModel, Session
from storage.utils import utcnow

__all__ = ["AuditLog", "audit_operation"]


class AuditLog(SQLModel, table=True):  # type: ignore[misc, call-arg]
    id: Optional[int] = Field(default=None, primary_key=True)

    # Queryable identifiers
    timestamp: datetime = Field(index=True)
    component: str = Field(index=True)
    record_id: int = Field(index=True)

    # What happened and by whom
    operation: str
    actor: str

    # Snapshot of state change
    before: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    after: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))


def audit_operation(
    *,
    session: Session,
    component: str,
    operation: str,
    record_id: int,
    actor: str,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Record a single audit event. Call this INSIDE the same transaction as the data change.
    """
    session.add(
        AuditLog(
            timestamp=utcnow(),
            component=component,
            record_id=record_id,
            operation=operation,
            actor=actor,
            before=before,
            after=after,
        )
    )
