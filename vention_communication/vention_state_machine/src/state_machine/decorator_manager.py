from typing import Any, Callable, cast
from vention_state_machine.src.state_machine.utils import wrap_with_timeout
from vention_state_machine.src.state_machine.machine_protocols import (
    StateMachineProtocol,
)
from typing_extensions import TypeAlias

StateCallbackBinding: TypeAlias = tuple[str, str, Any]
GuardBinding: TypeAlias = tuple[str, Callable[[], bool]]
StateChangeCallback: TypeAlias = Callable[[str, str, str], None]


class DecoratorManager:
    """
    Manages discovery and binding of decorator-based lifecycle hooks
    (`on_enter_state`, `on_exit_state`, `auto_timeout`, `guard`, and `on_state_change`) to a state machine instance.
    """

    def __init__(self, machine: StateMachineProtocol) -> None:
        self.machine = machine
        self._decorator_bindings: list[StateCallbackBinding] = []
        self._exit_decorator_bindings: list[StateCallbackBinding] = []
        self._guard_bindings: list[GuardBinding] = []
        self._state_change_callbacks: list[StateChangeCallback] = []

    def discover_decorated_handlers(self, target_class: type) -> None:
        """
        Collect decorated methods from a class definition.
        You must call this on the class object before instantiating.
        """
        for attr in dir(target_class):
            callback_fn = getattr(target_class, attr, None)
            if callable(callback_fn):
                self._discover_state_callbacks(callback_fn)
                self._discover_guard_conditions(callback_fn)
                self._discover_state_change_callbacks(callback_fn)

    def _discover_state_callbacks(self, callback_fn: Any) -> None:
        """Discover on_enter_state and on_exit_state decorators."""
        if hasattr(callback_fn, "_on_enter_state"):
            self._decorator_bindings.append(
                (callback_fn._on_enter_state, "enter", callback_fn)
            )

        if hasattr(callback_fn, "_on_exit_state"):
            self._exit_decorator_bindings.append(
                (callback_fn._on_exit_state, "exit", callback_fn)
            )

    def _discover_guard_conditions(self, callback_fn: Any) -> None:
        """Discover guard decorators."""
        if hasattr(callback_fn, "_guard_conditions"):
            for trigger_name, guard_fn in callback_fn._guard_conditions.items():
                self._guard_bindings.append((trigger_name, guard_fn))

    def _discover_state_change_callbacks(self, callback_fn: Any) -> None:
        """Discover on_state_change decorators."""
        if hasattr(callback_fn, "_state_change_callback"):
            state_change_callback = cast(StateChangeCallback, callback_fn)
            self._state_change_callbacks.append(state_change_callback)

    def bind_decorated_handlers(self, instance: Any) -> None:
        """
        After instantiating your class, call this with the instance.
        Hooks will be registered onto the state machine, and timeouts applied if needed.
        """
        self._bind_state_callbacks(instance)
        self._bind_guard_conditions(instance)
        self._bind_state_change_callbacks(instance)

    def _bind_state_callbacks(self, instance: Any) -> None:
        """Bind state entry/exit callbacks."""
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

    def _bind_guard_conditions(self, instance: Any) -> None:
        """Bind guard conditions."""
        for trigger_name, guard_fn in self._guard_bindings:
            bound_guard = guard_fn.__get__(instance)
            self.machine.add_transition_condition(trigger_name, bound_guard)

    def _bind_state_change_callbacks(self, instance: Any) -> None:
        """Bind state change callbacks."""
        for callback_fn in self._state_change_callbacks:
            bound_callback = callback_fn.__get__(instance)
            self.machine.add_state_change_callback(bound_callback)
