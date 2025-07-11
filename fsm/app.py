from fsm import FoundationFSM
import asyncio

STATES = [
    {
        "name": "running",
        "initial": "picking",
        "children": [
            {"name": "picking"},
            {"name": "placing"},
            {"name": "homing"},
        ],
    }
]

TRANSITIONS = [
    dict(trigger="start", source="ready", dest="running_picking"),
    dict(trigger="reset", source="fault", dest="ready"),
    dict(trigger="to_fault", source="*", dest="fault"),
    dict(trigger="timer_done", source="running_picking", dest="running_placing"),
    dict(trigger="move_done", source="running_placing", dest="running_homing"),
    dict(trigger="home_done", source="running_homing", dest="running_picking"),
]


class CellFSM(FoundationFSM):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.simulate_failure = False
        self.recover_at_last_motion = False
        self.last_state = None

    def to_fault(self):
        print(f"💾 Saved last state before fault: {self.last_state}")
        self.trigger("to_fault")

    def start(self):
        if self.recover_at_last_motion and self.last_state:
            print(f"🔄 Recovering at last state: {self.last_state}")
            self.set_state(self.last_state)
            self._invoke_on_enter(self.last_state)
        else:
            print("▶️ Starting from initial state (picking)")
            self.trigger("start")

    def _invoke_on_enter(self, state_name: str):
        handler_name = f"on_enter_{state_name}"
        handler = getattr(self, handler_name, None)
        if handler:
            handler(None)
        else:
            print(f"⚠️ No handler found for {handler_name}")

    def on_enter_running_picking(self, _):
        self._record_last_state()
        self._maybe_fail_or_continue(3, self.timer_done, "running_picking")

    def on_enter_running_placing(self, _):
        self._record_last_state()
        self._maybe_fail_or_continue(3, self.move_done, "running_placing")

    def on_enter_running_homing(self, _):
        self._record_last_state()
        self._maybe_fail_or_continue(3, self.home_done, "running_homing")

    def _record_last_state(self):
        self.last_state = self.state
        print(f"📌 Updated last_state to {self.last_state}")

    def _maybe_fail_or_continue(self, delay, trigger, expected_state):
        if self.simulate_failure:
            print(f"💥 Simulating failure in {self.state} in {delay}s")
            self.spawn(self._simulate_failure(delay, expected_state))
        else:
            print(f"➡️ Entering {self.state}: auto transition in {delay}s")
            self.spawn(self._delayed_trigger(delay, trigger, expected_state))

    async def _delayed_trigger(self, delay, trigger, expected_state):
        await asyncio.sleep(delay)
        if self.state == expected_state:
            trigger()
        else:
            print(f"⚠️ Skipping trigger because FSM moved from {expected_state} to {self.state}")

    async def _simulate_failure(self, delay, expected_state):
        await asyncio.sleep(delay)
        if self.state == expected_state:
            print(f"💥 Simulated error in {self.state}!")
            self.trigger("to_fault")
        else:
            print(f"⚠️ Skipping simulated failure because FSM moved from {expected_state} to {self.state}")