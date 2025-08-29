from __future__ import annotations

from collections import defaultdict
from typing import Callable, DefaultDict, Generic, List
from typing_extensions import Literal
from sqlmodel import Session
from storage.utils import ModelType

HookFn = Callable[[Session, ModelType], None]
HookEvent = Literal[
    "before_insert",
    "after_insert",
    "before_update",
    "after_update",
    "before_delete",
    "after_delete",
]


class HookRegistry(Generic[ModelType]):
    """Lightweight per-accessor registry for lifecycle hooks."""

    def __init__(self) -> None:
        self._hooks: DefaultDict[str, List[HookFn[ModelType]]] = defaultdict(list)

    def decorator(
        self, event: HookEvent
    ) -> Callable[[HookFn[ModelType]], HookFn[ModelType]]:
        """Return a decorator that registers a function for `event`."""

        def deco(fn: HookFn[ModelType]) -> HookFn[ModelType]:
            self._hooks[event].append(fn)
            return fn

        return deco

    def emit(self, event: HookEvent, *, session: Session, instance: ModelType) -> None:
        """Invoke all hooks registered for `event`."""
        for fn in self._hooks.get(event, []):
            fn(session, instance)
