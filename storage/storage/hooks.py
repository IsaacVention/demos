from __future__ import annotations

from typing import Callable, DefaultDict, Generic, List, TypeVar
from collections import defaultdict

from sqlmodel import Session, SQLModel
from typing_extensions import Literal

ModelRecord = TypeVar("ModelRecord", bound=SQLModel)

HookEvent = Literal[
    "before_insert",
    "after_insert",
    "before_update",
    "after_update",
    "before_delete",
    "after_delete",
]

HookFn = Callable[[Session, ModelRecord], None]


class HookRegistry(Generic[ModelRecord]):
    """Lightweight per-accessor registry for lifecycle hooks."""

    def __init__(self) -> None:
        self._hooks: DefaultDict[HookEvent, List[HookFn[ModelRecord]]] = defaultdict(
            list
        )

    def decorator(
        self, event: HookEvent
    ) -> Callable[[HookFn[ModelRecord]], HookFn[ModelRecord]]:
        """Return a decorator that registers a function for `event`."""

        def deco(fn: HookFn[ModelRecord]) -> HookFn[ModelRecord]:
            self._hooks[event].append(fn)
            return fn

        return deco

    def emit(
        self, event: HookEvent, *, session: Session, instance: ModelRecord
    ) -> None:
        """Invoke all hooks registered for `event`."""
        for fn in self._hooks.get(event, []):
            fn(session, instance)
