from __future__ import annotations
from typing import Any, Callable, Literal, Optional, Type, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .app import VentionApp
    from .entries import RpcBundle

from .entries import ActionEntry, StreamEntry
from .typing_utils import infer_input_type, infer_output_type, is_pydantic_model

_actions: List[ActionEntry] = []
_streams: List[StreamEntry] = []
_GLOBAL_APP: Optional["VentionApp"] = None


def set_global_app(app: Any) -> None:
    """Set the global app instance for use by stream publishers.

    Args:
        app: VentionApp instance to make globally available
    """
    global _GLOBAL_APP
    _GLOBAL_APP = app


def action(
    name: Optional[str] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register a function as an RPC action.

    Args:
        name: Optional name for the action. If not provided, uses the function name.

    Returns:
        Decorator function that registers the action
    """

    def decorator(function: Callable[..., Any]) -> Callable[..., Any]:
        input_type = infer_input_type(function)
        output_type = infer_output_type(function)
        entry = ActionEntry(
            name or function.__name__, function, input_type, output_type
        )
        _actions.append(entry)
        return function

    return decorator


def stream(
    name: str,
    *,
    payload: Type[Any],
    replay: bool = True,
    queue_maxsize: int = 1,
    policy: Literal["latest", "fifo"] = "latest",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a server-broadcast stream.

    The decorated function becomes a publisher that publishes its return value
    to the stream when called.

    Args:
        name: Name of the stream
        payload: Type of the payload (Pydantic model or JSON-serializable type)
        replay: Whether to replay the last value to new subscribers
        queue_maxsize: Maximum size of the per-subscriber queue
        policy: Delivery policy, either "latest" or "fifo"

    Returns:
        Decorator function that registers the stream
    """
    if not (is_pydantic_model(payload) or payload in (int, float, str, bool, dict)):
        raise ValueError(
            "payload must be a pydantic BaseModel or a JSON-serializable scalar/dict"
        )

    def decorator(function: Callable[..., Any]) -> Callable[..., Any]:
        entry = StreamEntry(
            name=name,
            func=None,
            payload_type=payload,
            replay=replay,
            queue_maxsize=queue_maxsize,
            policy=policy,
        )
        _streams.append(entry)

        async def publisher_wrapper(*args: Any, **kwargs: Any) -> Any:
            if _GLOBAL_APP is None or _GLOBAL_APP.connect_router is None:
                raise RuntimeError("Stream publish called before app.finalize()")
            result = await function(*args, **kwargs)
            _GLOBAL_APP.connect_router.publish(name, result)
            return None

        entry.func = publisher_wrapper
        return publisher_wrapper

    return decorator


def collect_bundle() -> RpcBundle:
    """Collect all registered actions and streams into an RpcBundle.

    Returns:
        RpcBundle containing all actions and streams registered via decorators
    """
    from .entries import RpcBundle

    return RpcBundle(actions=list(_actions), streams=list(_streams))
