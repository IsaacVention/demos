# src/vention_communication/decorators.py

"""
Decorators for defining RPC endpoints in Vention Communication.

@action() — unary RPC (request → response)
@stream(name, payload=…) — server-streaming RPC
"""

from typing import Any, Awaitable, Callable, Type, Optional, get_type_hints
from .entries import ActionEntry, StreamEntry
from .utils.typing_utils import get_input_type, get_return_type, Empty

# Module-level registries for definitions made outside of VentionApp
_actions: dict[str, ActionEntry] = {}
_streams: dict[str, StreamEntry] = {}


def action(name: Optional[str] = None):
    """
    Decorator for defining a unary RPC endpoint.
    Infers input_type and output_type from the function signature.
    """

    def decorator(fn: Callable[..., Awaitable[Any]]):
        rpc_name = name or fn.__name__

        input_type = get_input_type(fn)
        output_type = get_return_type(fn)

        entry = ActionEntry(
            name=rpc_name, fn=fn, input_type=input_type, output_type=output_type
        )

        _actions[rpc_name] = entry
        return fn

    return decorator


def stream(name: str, payload: Type[Any]):
    """
    Decorator for defining a server-streaming RPC.
    The wrapped function acts as the *publisher*.
    """
    def decorator(fn: Callable[..., Awaitable[Any]]):
        entry = StreamEntry(name=name, payload=payload, handler=fn, publisher=None)
        _streams[name] = entry

        async def publisher(*args: Any, **kwargs: Any):
            result = await fn(*args, **kwargs)
            from .app import _GLOBAL_APP  # reference injected below
            router = _GLOBAL_APP.connect_router
            manager = router.stream_handlers.get(name)
            if manager:
                await manager.publish(result)
            return result

        entry.publisher = publisher
        return publisher

    return decorator



def _get_registered_actions() -> dict[str, ActionEntry]:
    """Internal: get the module-level action entries."""
    return dict(_actions)


def _get_registered_streams() -> dict[str, StreamEntry]:
    """Internal: get the module-level stream entries."""
    return dict(_streams)


__all__ = ["action", "stream", "_get_registered_actions", "_get_registered_streams"]
