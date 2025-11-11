from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, Type


@dataclass
class ActionEntry:
    """Entry for a unary RPC action."""

    name: str
    func: Callable[..., Any]
    input_type: Optional[Type[Any]]
    output_type: Optional[Type[Any]]


@dataclass
class StreamEntry:
    """Entry for a streaming RPC."""

    name: str
    func: Optional[Callable[..., Any]]
    payload_type: Type[Any]
    replay: bool = True
    queue_maxsize: int = 1
    policy: Literal["latest", "fifo"] = "latest"


@dataclass
class RpcBundle:
    """Bundle of RPC actions and streams."""

    actions: list[ActionEntry] = field(default_factory=list)
    streams: list[StreamEntry] = field(default_factory=list)

    def extend(self, other: "RpcBundle") -> None:
        """Extend this bundle with actions and streams from another bundle.

        Args:
            other: RPC bundle to merge into this one
        """
        self.actions.extend(other.actions)
        self.streams.extend(other.streams)
