from typing import Protocol, Callable, Any


class SupportsTimeout(Protocol):
    def set_timeout(
        self, state_name: str, seconds: float, trigger_fn: Callable[[], str]
    ) -> None: ...


class SupportsStateCallbacks(Protocol):
    def get_state(self, state_name: str) -> Any: ...


class SupportsGuardConditions(Protocol):
    def add_transition_condition(
        self, trigger_name: str, condition_fn: Callable[[], bool]
    ) -> None: ...


class SupportsStateChangeCallbacks(Protocol):
    def add_state_change_callback(
        self, callback: Callable[[str, str, str], None]
    ) -> None: ...


class StateMachineProtocol(
    SupportsTimeout,
    SupportsStateCallbacks,
    SupportsGuardConditions,
    SupportsStateChangeCallbacks,
    Protocol,
):
    """Combined protocol for state machine interface."""
