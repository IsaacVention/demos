from fsm import FoundationFSM
import asyncio

STATES = [
    {
        "name": "running",
        "initial": "picking",
        "children": [
            {"name": "picking"},
            {"name": "placing"},
        ],
    }
]

TRANSITIONS = [
    dict(trigger="start", source="ready", dest="running_picking"),
    dict(trigger="reset", source="fault", dest="ready"),
    dict(trigger="to_fault", source="*", dest="fault"),
    dict(trigger="timer_done", source="running_picking", dest="running_placing"),
    dict(trigger="move_done", source="running_placing", dest="running_picking"),
]


class CellFSM(FoundationFSM):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.simulate_failure = False

    def on_enter_running_picking(self, _):
        print("🎯 Entering PICKING: will auto transition in 5s")
        self.spawn(self._delayed_trigger(5, self.timer_done))

    def on_enter_running_placing(self, _):
        if self.simulate_failure:
            print("🚚 Entering PLACING: will fail in 5s (simulate_failure=True)")
            self.spawn(self._simulate_failure(5))
        else:
            print("🚚 Entering PLACING: will auto transition in 5s")
            self.spawn(self._delayed_trigger(5, self.move_done))

    async def _delayed_trigger(self, delay, trigger):
        await asyncio.sleep(delay)
        trigger()

    async def _simulate_failure(self, delay):
        await asyncio.sleep(delay)
        print("💥 Simulated error in PLACING!")
        self.to_fault()