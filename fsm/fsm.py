import asyncio
from transitions.extensions.asyncio import HierarchicalMachine as HSM

class FoundationFSM(HSM):
    def __init__(
        self,
        *args,
        states=None,
        enable_last_state_recovery=True,
        **kw,
    ):
        super().__init__(
            states=(states or []) + ["ready", "fault"],
            initial="ready",
            send_event=True,
            **kw,
        )
        self._declared_states = states or []
        self._tasks: set[asyncio.Task] = set()
        self._last_state = None
        self._enable_recovery = enable_last_state_recovery

        self.add_transition("to_fault", "*", "fault", before="cancel_tasks")
        self.add_transition("reset", "fault", "ready")
        self._attach_after_hooks()

    def spawn(self, coro):
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(lambda _: self._tasks.discard(t))
        return t

    async def cancel_tasks(self, *_):
        for t in list(self._tasks):
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

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