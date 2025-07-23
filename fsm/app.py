import asyncio
from fsm import FoundationFSM, on_enter_state, on_exit_state, auto_timeout

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
    dict(trigger="finished_picking", source="running_picking", dest="running_placing"),
    dict(trigger="finished_placing", source="running_placing", dest="running_homing"),
    dict(trigger="finished_homing", source="running_homing", dest="running_picking"),
]

class CellFSM(FoundationFSM):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("enable_last_state_recovery", False)
        super().__init__(*args, **kwargs)
        self.simulate_failure = False

    @on_enter_state("running_picking")
    @auto_timeout(5.0, "to_fault")
    def enter_picking(self, _):
        print("entering picking")
        self._maybe_fail_or_continue(3, self.finished_picking, "running_picking")

    @on_enter_state("running_placing")
    def enter_placing(self, _):
        print("entering placing")
        self._maybe_fail_or_continue(3, self.finished_placing, "running_placing")

    @on_enter_state("running_homing")
    def enter_homing(self, _):
        print("entering homing")
        self._maybe_fail_or_continue(3, self.finished_homing, "running_homing")

    def _maybe_fail_or_continue(self, delay, trigger, expected_state):
        if self.simulate_failure:
            self.spawn(self._simulate_failure(delay, expected_state))
        else:
            self.spawn(self._delayed_trigger(delay, trigger, expected_state))

    async def _delayed_trigger(self, delay, trigger, expected_state):
        await asyncio.sleep(delay)
        if self.state == expected_state:
            trigger()

    async def _simulate_failure(self, delay, expected_state):
        await asyncio.sleep(delay)
        print(f"{self.state} : {expected_state}")
        if self.state == expected_state:
            self.to_fault()