from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Type

@dataclass
class ActionEntry:
    name: str
    fn: Callable[..., Awaitable[Any]]
    input_type: Type
    output_type: Type

@dataclass
class StreamEntry:
    name: str
    payload: Type
    handler: Callable[..., Awaitable[Any]]
    publisher: Callable[..., Awaitable[None]]

@dataclass
class RpcBundle:
    actions: dict[str, ActionEntry]
    streams: dict[str, StreamEntry]
