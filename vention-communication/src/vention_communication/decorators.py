# decorators.py

from __future__ import annotations
from typing import Any, Callable, Optional, Type, Dict, List

from fastapi import utils
from pydantic import BaseModel
from google.protobuf.empty_pb2 import Empty as _Empty  # type: ignore

from .entries import ActionEntry, StreamEntry
from .typing_utils import infer_input_type, infer_output_type, is_pydantic_model

# Global registries populated by decorators (kept for compatibility)
_actions: List[ActionEntry] = []
_streams: List[StreamEntry] = []

# Set by VentionApp.finalize()
_GLOBAL_APP = None  # type: ignore


def set_global_app(app: Any) -> None:
    global _GLOBAL_APP
    _GLOBAL_APP = app


# ----------------- Actions (unary) -----------------


def action(
    name: Optional[str] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        in_t = infer_input_type(fn)  # None → Empty
        out_t = infer_output_type(fn)  # None → Empty
        entry = ActionEntry(name or fn.__name__, fn, in_t, out_t)
        _actions.append(entry)
        return fn

    return decorator


# ----------------- Streams (server broadcast) -----------------


def stream(
    name: str,
    *,
    payload: Type[Any],
    replay: bool = True,
    queue_maxsize: int = 1,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Register a server-broadcast stream. The decorated function becomes a PUBLISHER:
    - When you call it, we await your function, then publish its return value to the stream.
    """
    if not (is_pydantic_model(payload) or payload in (int, float, str, bool, dict)):
        # keep scalar+model coverage for now
        raise ValueError(
            "payload must be a pydantic BaseModel or a JSON-serializable scalar/dict"
        )

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        entry = StreamEntry(
            name=name,
            func=None,  # filled by wrapper
            payload_type=payload,
            replay=replay,
            queue_maxsize=queue_maxsize,
        )
        _streams.append(entry)

        async def publisher_wrapper(*args: Any, **kwargs: Any) -> Any:
            if _GLOBAL_APP is None or _GLOBAL_APP.connect_router is None:
                raise RuntimeError("Stream publish called before app.finalize()")
            result = await fn(*args, **kwargs)
            # Publish into the manager (latest-wins distribution)
            _GLOBAL_APP.connect_router.publish(name, result)
            return None

        entry.func = publisher_wrapper  # type: ignore
        return publisher_wrapper

    return decorator


# --------------- Export for app/codegen ----------------


def collect_bundle():
    from .entries import RpcBundle

    return RpcBundle(actions=list(_actions), streams=list(_streams))
