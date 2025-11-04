from typing import Union, Callable, cast
from .defs import State, Trigger
from .decorator_protocols import (
    SupportsGuardConditions,
    SupportsStateChangeCallback,
    SupportsEnterState,
    SupportsExitState,
    SupportsTimeoutConfig,
    CallableType,
)


def on_enter_state(
    state_node: Union[str, State],
) -> Callable[[CallableType], CallableType]:
    """
    Decorator to bind a function to the on-enter hook for a state.
    Accepts a str or a State descriptor.
    """
    if hasattr(state_node, "name"):
        state_name = state_node.name
    elif isinstance(state_node, str):
        state_name = state_node
    else:
        raise TypeError(f"Expected a State or str, got {type(state_node)}")

    def decorator(fn: CallableType) -> CallableType:
        enter_fn: SupportsEnterState = cast(SupportsEnterState, fn)
        enter_fn._on_enter_state = state_name
        return fn

    return decorator


def on_exit_state(
    state_node: Union[str, State],
) -> Callable[[CallableType], CallableType]:
    """
    Decorator to bind a function to the on-exit hook for a state.
    Accepts a str or a State descriptor.
    """
    if hasattr(state_node, "name"):
        state_name = state_node.name
    elif isinstance(state_node, str):
        state_name = state_node
    else:
        raise TypeError(f"Expected a State or str, got {type(state_node)}")

    def decorator(fn: CallableType) -> CallableType:
        exit_fn: SupportsExitState = cast(SupportsExitState, fn)
        exit_fn._on_exit_state = state_name
        return fn

    return decorator


def auto_timeout(
    seconds: float, trigger: Union[str, Callable[[], str]] = "to_fault"
) -> Callable[[CallableType], CallableType]:
    """
    Decorator that applies an auto-timeout configuration to a state entry handler.
    """

    def decorator(fn: CallableType) -> CallableType:
        timeout_fn: SupportsTimeoutConfig = cast(SupportsTimeoutConfig, fn)
        timeout_fn._timeout_config = (seconds, trigger)
        return fn

    return decorator


def guard(
    *triggers: Union[str, Trigger],
) -> Callable[[CallableType], CallableType]:
    """
    Decorator to add a guard condition to one or more transition triggers.
    The decorated function should return a boolean indicating whether the transition is allowed.
    Accepts multiple str or Trigger descriptors.

    Examples:
        @guard(Triggers.reset)  # Single trigger
        @guard(Triggers.reset, Triggers.start)  # Multiple triggers
        @guard("reset", "start")  # Multiple string triggers
    """

    def decorator(fn: CallableType) -> CallableType:
        guard_fn: SupportsGuardConditions = cast(SupportsGuardConditions, fn)

        if not hasattr(guard_fn, "_guard_conditions"):
            guard_fn._guard_conditions = {}

        for trigger in triggers:
            trigger_name = (
                getattr(trigger, "name", trigger)
                if hasattr(trigger, "name")
                else trigger
            )
            if not isinstance(trigger_name, str):
                raise TypeError(f"Expected a Trigger or str, got {type(trigger)}")

            guard_fn._guard_conditions[trigger_name] = fn

        return fn

    return decorator


def on_state_change(fn: CallableType) -> CallableType:
    """
    Decorator to register a global state change callback.
    The decorated function will be called whenever any state transition occurs.
    The callback receives (old_state, new_state, trigger_name) as arguments.
    """
    callback_fn: SupportsStateChangeCallback = cast(SupportsStateChangeCallback, fn)
    callback_fn._state_change_callback = True
    return fn
