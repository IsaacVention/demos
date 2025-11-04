from datetime import datetime, timezone, date, time
from typing import Literal, TypeVar, Any
from sqlmodel import SQLModel

ModelType = TypeVar("ModelType", bound=SQLModel)
Operation = Literal["create", "update", "delete", "soft_delete", "restore"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_primitive(value: Any) -> Any:
    """
    Convert Python values to CSV/JSON-friendly scalars.
    Datetime/date/time -> ISO 8601 strings; others unchanged.
    """
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value
