from typing import Any, Callable, Union
from vention_state_machine.src.state_machine.defs import StateGroup


def wrap_with_timeout(
    handler: Callable[[Any], Any],
    state_name: str,
    timeout: tuple[float, Union[str, Callable[[], str]]],
    set_timeout_fn: Callable[[str, float, Callable[[], str]], None],
) -> Callable[[Any], Any]:
    """
    Wraps a state entry handler with timeout behavior.

    Args:
        handler: The original state entry function to wrap.
        state_name: The name of the state for which the timeout applies.
        timeout: A tuple containing (seconds, trigger), where:
            - seconds: Timeout duration in seconds.
            - trigger: A string (trigger name) or a function returning a trigger name.
        set_timeout_fn: A function used to register the timeout with the FSM. Signature:
            (state_name: str, seconds: float, trigger_fn: () -> str) -> None

    Returns:
        A new function that sets the timeout and then invokes the original handler.
    """
    seconds, trig = timeout

    if isinstance(trig, str):

        def trigger_fn() -> str:
            return trig
    elif callable(trig):
        trigger_fn = trig
    else:
        raise TypeError(f"Unsupported trigger type: {type(trig).__name__}")

    def wrapped(event: Any) -> Any:
        set_timeout_fn(state_name, seconds, trigger_fn)
        return handler(event)

    return wrapped


def is_state_container(state_source: object) -> bool:
    """
    Return True if `obj` is an instance or class that contains StateGroup(s).
    """
    try:
        return any(
            isinstance(value, StateGroup) for value in vars(state_source).values()
        ) or any(
            isinstance(value, StateGroup)
            for value in vars(state_source.__class__).values()
        )
    except TypeError:
        return False
