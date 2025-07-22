import asyncio
from transitions.extensions.asyncio import HierarchicalMachine as HSM

class FoundationFSM(HSM):
    def __init__(self, *args, states=None, enable_last_state_recovery=True, **kw):
        self._decorator_bindings = []
        self._exit_decorator_bindings = []
        self._declared_states = states or []

        self._discover_decorated_handlers()
        super().__init__(
            states=(states or []) + ["ready", "fault"],
            initial="ready",
            send_event=True,
            **kw,
        )

        self._bind_decorated_handlers()

        # Init rest
        self._declared_states = states or []
        self._tasks = set()
        self._timeouts = {}
        self._last_state = None
        self._enable_recovery = enable_last_state_recovery
        self.add_transition("to_fault", "*", "fault", before="cancel_tasks")
        self.add_transition("reset", "fault", "ready")
        self._attach_after_hooks()

    # ---------- Task Lifecycle ----------
    def spawn(self, coro):
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(lambda _: self._tasks.discard(t))
        return t

    async def cancel_tasks(self, *_):
        self._clear_all_timeouts()
        for t in list(self._tasks):
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

    # ---------- Timeout API ----------
    def set_timeout(self, state_name: str, seconds: float, trigger: str):
        self._clear_timeout(state_name)
        async def timeout_task():
            await asyncio.sleep(seconds)
            if self.state == state_name:
                self.trigger(trigger)

        self._timeouts[state_name] = self.spawn(timeout_task())

    def _clear_timeout(self, state_name: str):
        task = self._timeouts.pop(state_name, None)
        if task:
            task.cancel()

    def _clear_all_timeouts(self):
        for task in self._timeouts.values():
            task.cancel()
        self._timeouts.clear()

    # ---------- Recovery ----------
    def record_last_state(self):
        self._last_state = self.state

    def get_last_state(self):
        return self._last_state

    def start(self):
        if self._enable_recovery and self._last_state:
            self.set_state(self._last_state)
            self._invoke_on_enter(self._last_state)
        else:
            self.trigger("start")

    def _invoke_on_enter(self, state_name: str):
        handler_name = f"on_enter_{state_name}"
        handler = getattr(self, handler_name, None)
        if handler:
            handler(None)

    def on_enter_ready(self, _):
        if not self._enable_recovery:
            self._last_state = None

    # ---------- Hooks ----------
    def _record_last_state_event(self, event):
        if event.state.name in ("ready", "fault"):
            return
        if not getattr(event.state, "children", []):
            self._last_state = event.transition.dest

    def _attach_after_hooks(self):
        for trigger_name, event in self.events.items():
            if trigger_name in ("reset",):
                continue
            for transitions_for_source in event.transitions.values():
                for t in transitions_for_source:
                    t.add_callback("after", self._record_last_state_event)
                    t.add_callback("after", self._attach_exit_timeout_clear)
    def _attach_exit_timeout_clear(self, event):
        exited_state = event.transition.source
        self._clear_timeout(exited_state)
        
    # ---------- Decorators ----------
    def _discover_decorated_handlers(self):
        for attr in dir(self.__class__):
            fn = getattr(self.__class__, attr, None)
            if callable(fn) and hasattr(fn, "_on_enter_state"):
                state = fn._on_enter_state
                self._decorator_bindings.append((state, "enter", fn))
            if callable(fn) and hasattr(fn, "_on_exit_state"):
                self._exit_decorator_bindings.append((fn._on_exit_state, "exit", fn))

    def _bind_decorated_handlers(self):
        for state_name, hook_type, fn in self._decorator_bindings + self._exit_decorator_bindings:
            base_handler = fn.__get__(self)
            if hook_type == "enter":
                timeout_cfg = getattr(fn, "_timeout_config", None)
                if timeout_cfg:
                    seconds, trigger = timeout_cfg
                    def make_wrapped(base_handler, state, seconds, trigger):
                        def wrapped(event):
                            self.set_timeout(state, seconds, trigger)
                            return base_handler(event)
                        return wrapped
                    handler = make_wrapped(base_handler, state_name, seconds, trigger)
                else:
                    handler = base_handler
            else:
                handler = base_handler

            state_obj = self.get_state(state_name)
            if state_obj:
                state_obj.add_callback(hook_type, handler)
                
def on_enter_state(state_name: str):
    def decorator(fn):
        fn._on_enter_state = state_name
        return fn
    return decorator

def on_exit_state(state_name: str):
    def decorator(fn):
        fn._on_exit_state = state_name
        return fn
    return decorator

def auto_timeout(seconds: float, trigger: str = "to_fault"):
    def decorator(fn):
        fn._timeout_config = (seconds, trigger)
        return fn
    return decorator
