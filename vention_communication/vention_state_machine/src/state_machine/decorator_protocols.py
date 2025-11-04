from typing import Protocol, Callable, Any, Union

CallableType = Callable[..., Any]


class SupportsGuardConditions(Protocol):
    _guard_conditions: dict[str, CallableType]


class SupportsStateChangeCallback(Protocol):
    _state_change_callback: bool


class SupportsEnterState(Protocol):
    _on_enter_state: str


class SupportsExitState(Protocol):
    _on_exit_state: str


class SupportsTimeoutConfig(Protocol):
    _timeout_config: tuple[float, Union[str, Callable[[], str]]]
