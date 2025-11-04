# errors.py

from __future__ import annotations
from typing import Any, Dict, Optional, Tuple, Type


# --- Connect-style error envelope -------------------------

CONNECT_CODE_MAP = {
    "cancelled": "cancelled",
    "unknown": "unknown",
    "invalid_argument": "invalid_argument",
    "deadline_exceeded": "deadline_exceeded",
    "not_found": "not_found",
    "already_exists": "already_exists",
    "permission_denied": "permission_denied",
    "resource_exhausted": "resource_exhausted",
    "failed_precondition": "failed_precondition",
    "aborted": "aborted",
    "out_of_range": "out_of_range",
    "unimplemented": "unimplemented",
    "internal": "internal",
    "unavailable": "unavailable",
    "data_loss": "data_loss",
    "unauthenticated": "unauthenticated",
}


class ConnectError(Exception):
    """Application-level error to send over Connect transport."""

    def __init__(self, code: str, message: str, *, details: Optional[list] = None) -> None:
        super().__init__(message)
        if code not in CONNECT_CODE_MAP:
            code = "unknown"
        self.code = code
        self.message = message
        self.details = details or []


def to_connect_error(exc: BaseException) -> ConnectError:
    """Map arbitrary exceptions to a ConnectError (best-effort)."""
    if isinstance(exc, ConnectError):
        return exc

    # Light heuristic mapping; customize as needed.
    import asyncio
    if isinstance(exc, asyncio.TimeoutError):
        return ConnectError("deadline_exceeded", str(exc) or "Deadline exceeded")

    if isinstance(exc, (KeyError, ValueError)):
        return ConnectError("invalid_argument", str(exc) or "Invalid argument")

    if isinstance(exc, PermissionError):
        return ConnectError("permission_denied", str(exc) or "Permission denied")

    # Default
    return ConnectError("internal", str(exc) or exc.__class__.__name__)


def error_envelope(exc: BaseException) -> Dict[str, Any]:
    ce = to_connect_error(exc)
    return {"error": {"code": ce.code, "message": ce.message, "details": ce.details}}
