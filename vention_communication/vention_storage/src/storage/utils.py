from datetime import datetime, timezone, date, time
from typing import Literal, TypeVar, Any, Optional
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


def parse_audit_operation(operation: Optional[str]) -> Optional[Operation]:
    """
    Parse and validate an operation string for audit queries.
    
    Args:
        operation: Operation string to parse
        
    Returns:
        Validated Operation literal or None
        
    Raises:
        ValueError: If operation string is invalid
    """
    if operation is None:
        return None
    
    valid_operations = ("create", "update", "delete", "soft_delete", "restore")
    if operation not in valid_operations:
        raise ValueError(f"Invalid operation: {operation}. Must be one of {valid_operations}")
    
    return operation  # type: ignore


def parse_audit_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO 8601 datetime string for audit queries.
    Handles both 'Z' and '+00:00' timezone formats.
    
    Args:
        dt_str: ISO 8601 datetime string
        
    Returns:
        Parsed datetime or None
    """
    if dt_str is None:
        return None
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
