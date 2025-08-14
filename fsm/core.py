# mypy: disable-error-code=misc

import asyncio
from collections import deque
from collections.abc import Coroutine
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol, Union
from transitions.extensions import HierarchicalGraphMachine
from transitions.core import State
from defs import StateGroup
from enum import Enum
from decorator_manager import DecoratorManager
from utils import is_state_container


class SupportsTimeout(Protocol):
    def set_timeout(
        self, state_name: str, seconds: float, trigger_fn: Callable[[], str]
    ) -> None: ...


class BaseStates(str, Enum):
    """Base states that all state machines include."""

    READY = "ready"
    FAULT = "fault"


class BaseTriggers(str, Enum):
    """Base triggers that all state machines include."""

    START = "start"
    RESET = "reset"
    TO_FAULT = "to_fault"


StateDict = dict[str, object]

class StateMachine(HierarchicalGraphMachine):
    """
    State Machine wrapping `HierarchicalGraphMachine` with:
      - Default states: 'ready', 'fault'
      - Global transitions: 'to_fault', 'reset'
      - Async task tracking (spawn/cancel)
      - Auto-timeout support via decorator
      - Recoverable last-state functionality
      - Transition history recording
      - Decorator-based entry/exit hooks
    """

    DEFAULT_HISTORY_SIZE: int = 1000

    def __init__(
        self,
        states: Union[object, list[StateDict], None] = None,
        *,
        transitions: Optional[list[dict[str, str]]] = None,
        history_size: Optional[int] = None,
        enable_last_state_recovery: bool = True,
        **kw: Any,
    ) -> None:
        # Normalize state definitions
        if is_state_container(states):
            state_groups = [
                value
                for value in vars(states).values()
                if isinstance(value, StateGroup)
            ]
            resolved_states = [group.to_state_list()[0] for group in state_groups]
        elif isinstance(states, list):
            resolved_states = states
        else:
            raise TypeError(
                f"`states` must be either a StateGroup container or a list of state dicts. "
                f"Got: {type(states).__name__}"
            )

        self._declared_states: list[dict[str, Any]] = resolved_states

        self._decorator_manager = DecoratorManager(self)
        self._decorator_manager.discover_decorated_handlers(self.__class__)

        # Initialize base machine
        combined_states = self._declared_states + [
            BaseStates.READY.value,
            BaseStates.FAULT.value,
        ]
        super().__init__(
            states=combined_states,
            transitions=transitions or [],
            initial="ready",
            send_event=True,
            **kw,
        )

        # Internal tracking
        self._tasks: set[asyncio.Task[Any]] = set()
        self._timeouts: dict[str, asyncio.Task[Any]] = {}
        self._last_state: Optional[str] = None
        self._enable_recovery: bool = enable_last_state_recovery
        self._history: deque[dict[str, Any]] = deque(
            maxlen=history_size or self.DEFAULT_HISTORY_SIZE
        )
        self._current_start: Optional[datetime] = None

        self._decorator_manager.bind_decorated_handlers(self)
        self._add_recovery_transitions()
        self.add_transition(
            BaseTriggers.TO_FAULT.value,
            "*",
            BaseStates.FAULT.value,
            before="cancel_tasks",
        )
        self.add_transition(
            BaseTriggers.RESET.value, BaseStates.FAULT.value, BaseStates.READY.value
        )
        self._attach_after_hooks()

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        """
        Start an async background task and track it for potential cancellation.
        """
        task: asyncio.Task[Any] = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(lambda _: self._tasks.discard(task))
        return task

    async def cancel_tasks(self, *_: Any) -> None:
        """
        Cancel all tracked background tasks and clear any timeouts.
        """
        self._clear_all_timeouts()
        for task in list(self._tasks):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def set_timeout(
        self, state_name: str, seconds: float, trigger_fn: Callable[[], str]
    ) -> None:
        """
        Schedule a timeout: if `state_name` remains active after `seconds`, fire `trigger_fn()`.
        """
        self._clear_timeout(state_name)

        async def _timeout_task() -> None:
            await asyncio.sleep(seconds)
            if self.state == state_name:
                self.trigger(trigger_fn())

        self._timeouts[state_name] = self.spawn(_timeout_task())

    def _clear_timeout(self, state_name: str) -> None:
        """Cancel a pending timeout for the given state."""
        task = self._timeouts.pop(state_name, None)
        if task:
            task.cancel()

    def _clear_all_timeouts(self) -> None:
        """Cancel all pending state timeouts."""
        for timeout in self._timeouts.values():
            timeout.cancel()
        self._timeouts.clear()

    def record_last_state(self) -> None:
        """Manually record the current state for later recovery."""
        self._last_state = self.state

    def get_last_state(self) -> Optional[str]:
        """Get the most recently recorded recoverable state."""
        return self._last_state

    def start(self) -> None:
        """
        Enter the machine: if recovery is enabled and a state was recorded, fire the
        corresponding recover__ transition; otherwise fire 'start'.
        """
        if self._enable_recovery and self._last_state:
            self.trigger(f"recover__{self._last_state}")
        else:
            self.trigger(BaseTriggers.START.value)

    @property
    def history(self) -> list[dict[str, Any]]:
        """Get the full transition history with timestamps and durations."""
        return list(self._history)

    def get_last_history_entries(self, n: int = 10) -> list[dict[str, Any]]:
        """Get the last `n` history entries."""
        return list(self._history)[-n:] if n > 0 else []

    # -- Private helpers --
    def _run_enter_callbacks(self, state_name: str) -> None:
        state_obj = self.get_state(state_name)
        for callback in getattr(state_obj, "enter", []):
            callback(None)

    def on_enter_ready(self, _: Any) -> None:
        if not self._enable_recovery:
            self._last_state = None

    def _is_leaf(self, state: Union[State, str]) -> bool:
        state_data = self.get_state(state) if isinstance(state, str) else state
        return not getattr(state_data, "children", [])

    def _record_history_event(self, event: Any) -> None:
        now = datetime.now(timezone.utc)
        dest = event.transition.dest
        if self._history and self._current_start is not None:
            elapsed = (now - self._current_start).total_seconds() * 1000
            self._history[-1]["duration_ms"] = int(elapsed)
        self._history.append({"timestamp": now, "state": dest})
        self._current_start = now
        if self._is_leaf(dest) and dest not in {
            BaseStates.READY.value,
            BaseStates.FAULT.value,
        }:
            self._last_state = dest

    def _attach_after_hooks(self) -> None:
        for _, event in self.events.items():
            for transitions_for_source in event.transitions.values():
                for transition in transitions_for_source:
                    transition.add_callback("after", self._record_history_event)
                    transition.add_callback("after", self._attach_exit_timeout_clear)

    def _attach_exit_timeout_clear(self, event: Any) -> None:
        self._clear_timeout(event.transition.source)

    def _add_recovery_transitions(self) -> None:
        for state_spec in self._declared_states:
            parent_name = state_spec["name"]
            for child_spec in state_spec.get("children", []):
                full_state_name = f"{parent_name}_{child_spec['name']}"
                self.add_transition(
                    f"recover__{full_state_name}",
                    BaseStates.READY.value,
                    full_state_name,
                )
