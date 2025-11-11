from __future__ import annotations
from typing import Any, Dict, List, Optional


class ConnectError(Exception):
    """Application-level error to send over Connect transport."""

    def __init__(
        self, code: str, message: str, *, details: Optional[List[Any]] = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []


def to_connect_error(exception: BaseException) -> ConnectError:
    """Map arbitrary exceptions to a ConnectError.

    Args:
        exception: Exception to convert

    Returns:
        ConnectError with appropriate error code based on exception type
    """
    if isinstance(exception, ConnectError):
        return exception

    import asyncio

    if isinstance(exception, asyncio.TimeoutError):
        return ConnectError("deadline_exceeded", str(exception) or "Deadline exceeded")

    if isinstance(exception, (KeyError, ValueError)):
        return ConnectError("invalid_argument", str(exception) or "Invalid argument")

    if isinstance(exception, PermissionError):
        return ConnectError("permission_denied", str(exception) or "Permission denied")

    return ConnectError("internal", str(exception) or exception.__class__.__name__)


def error_envelope(exception: BaseException) -> Dict[str, Any]:
    """Wrap an exception in a Connect error envelope format.

    Args:
        exception: Exception to wrap

    Returns:
        Dictionary with error code, message, and details in Connect format
    """
    connect_error = to_connect_error(exception)
    return {
        "error": {
            "code": connect_error.code,
            "message": connect_error.message,
            "details": connect_error.details,
        }
    }
