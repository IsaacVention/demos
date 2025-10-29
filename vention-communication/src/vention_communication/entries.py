# entries.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Type


@dataclass
class ActionEntry:
    name: str
    func: Callable[..., Any]
    input_type: Optional[Type[Any]]
    output_type: Optional[Type[Any]]


@dataclass
class StreamEntry:
    name: str
    func: Callable[..., Any]  # publisher wrapper
    payload_type: Type[Any]
    # --- New, configurable behavior ---
    replay: bool = True  # enqueue last_value on new subscriber
    queue_maxsize: int = 1  # per-subscriber buffer; 1 = latest-wins


@dataclass
class RpcBundle:
    actions: list[ActionEntry] = field(default_factory=list)
    streams: list[StreamEntry] = field(default_factory=list)

    def extend(self, other: "RpcBundle") -> None:
        self.actions.extend(other.actions)
        self.streams.extend(other.streams)
