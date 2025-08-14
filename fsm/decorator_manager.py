from typing import Any, Callable, Protocol
from utils import wrap_with_timeout


class SupportsTimeout(Protocol):
    def set_timeout(
        self, state_name: str, seconds: float, trigger_fn: Callable[[], str]
    ) -> None: ...


class SupportsStateCallbacks(Protocol):
    def get_state(self, state_name: str) -> Any: ...


class StateMachineProtocol(SupportsTimeout, SupportsStateCallbacks, Protocol):
    """
    Combined protocol to describe the expected surface area of a compatible state machine:
    - .get_state(name) → returns state object with .add_callback(hook_type, fn)
    - .set_timeout(state_name, seconds, trigger_fn) → used for auto_timeout decorator
    """


class DecoratorManager:
    """
    Manages discovery and binding of decorator-based lifecycle hooks
    (`on_enter_state`, `on_exit_state`, and `auto_timeout`) to a state machine instance.
    """

    def __init__(self, machine: StateMachineProtocol) -> None:
        self.machine = machine
        self._decorator_bindings: list[tuple[str, str, Callable[[Any], Any]]] = []
        self._exit_decorator_bindings: list[tuple[str, str, Callable[[Any], Any]]] = []

    def discover_decorated_handlers(self, target_class: type) -> None:
        """
        Collect decorated methods from a class definition.
        You must call this on the class object before instantiating.
        """
        for attr in dir(target_class):
            callback_fn = getattr(target_class, attr, None)
            if callable(callback_fn) and hasattr(callback_fn, "_on_enter_state"):
                self._decorator_bindings.append(
                    (callback_fn._on_enter_state, "enter", callback_fn)
                )
            if callable(callback_fn) and hasattr(callback_fn, "_on_exit_state"):
                self._exit_decorator_bindings.append(
                    (callback_fn._on_exit_state, "exit", callback_fn)
                )

    def bind_decorated_handlers(self, instance: Any) -> None:
        """
        After instantiating your class, call this with the instance.
        Hooks will be registered onto the state machine, and timeouts applied if needed.
        """
        for state_name, hook_type, callback_fn in (
            self._decorator_bindings + self._exit_decorator_bindings
        ):
            bound_fn = callback_fn.__get__(instance)

            if hook_type == "enter" and hasattr(callback_fn, "_timeout_config"):
                handler = wrap_with_timeout(
                    bound_fn,
                    state_name,
                    callback_fn._timeout_config,
                    self.machine.set_timeout,
                )
            else:
                handler = bound_fn

            state_obj = self.machine.get_state(state_name)
            if state_obj:
                state_obj.add_callback(hook_type, handler)
