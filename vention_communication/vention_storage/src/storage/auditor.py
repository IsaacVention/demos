from __future__ import annotations

from datetime import datetime, date
from typing import Any, Dict, Optional, cast

from sqlalchemy import Column, String
from sqlalchemy.dialects.sqlite import JSON
from sqlmodel import Field, SQLModel, Session
from vention_storage.src.storage.utils import utcnow, Operation
import json

__all__ = ["AuditLog", "audit_operation"]


class AuditLog(SQLModel, table=True):  # type: ignore[misc, call-arg]
    id: Optional[int] = Field(default=None, primary_key=True)

    # Queryable identifiers
    timestamp: datetime = Field(index=True)
    component: str = Field(index=True)
    record_id: int = Field(index=True)

    # What happened and by whom
    operation: Operation = Field(sa_column=Column(String, nullable=False))
    actor: str

    # Snapshot of state change
    before: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    after: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    # add more cases as needed
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _jsonify(value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    # round-trip through json to coerce unsupported types (e.g., datetime) into strings
    return cast(Dict[str, Any], json.loads(json.dumps(value, default=_json_default)))


def audit_operation(
    *,
    session: Session,
    component: str,
    operation: Operation,
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
            before=_jsonify(before),
            after=_jsonify(after),
        )
    )
