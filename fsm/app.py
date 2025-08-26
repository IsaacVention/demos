import asyncio
from state_machine.core import StateMachine
from state_machine.defs import StateGroup, State, Trigger
from state_machine.decorators import on_enter_state, auto_timeout
from state_machine.core import BaseStates, BaseTriggers


# ---------- State , Trigger & Transition Declarations ----------


class RunningStates(StateGroup):
    picking: State = State()
    placing: State = State()
    homing: State = State()


class States:
    running = RunningStates()


class Triggers:
    start = Trigger("start")
    finished_picking = Trigger("finished_picking")
    finished_placing = Trigger("finished_placing")
    finished_homing = Trigger("finished_homing")
    to_fault = Trigger("to_fault")
    reset = Trigger("reset")


TRANSITIONS = [
    Triggers.start.transition("ready", States.running.picking),
    Triggers.finished_picking.transition(States.running.picking, States.running.placing),
    Triggers.finished_placing.transition(States.running.placing, States.running.homing),
    Triggers.finished_homing.transition(States.running.homing, States.running.picking),
]

# ---------- FSM Implementation ----------


class CellFSM(StateMachine):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("enable_last_state_recovery", False)
        kwargs.setdefault("states", States)
        kwargs.setdefault("transitions", TRANSITIONS)
        super().__init__(*args, **kwargs)
        self.simulate_failure = False
        
    @on_enter_state(BaseStates.READY.value)
    @auto_timeout(5.0, BaseTriggers.TO_FAULT.value)
    def enter_fault(self, _):
        print("🔴 entering ready")

    
    @on_enter_state(States.running.picking)
    @auto_timeout(5.0, Triggers.to_fault)
    def enter_picking(self, _):
        print("🟢 entering picking")
        self._maybe_fail_or_continue(
            3, Triggers.finished_picking, States.running.picking
        )

    @on_enter_state(States.running.placing)
    def enter_placing(self, _):
        print("🟡 entering placing")
        self._maybe_fail_or_continue(
            3, Triggers.finished_placing, States.running.placing
        )

    @on_enter_state(States.running.homing)
    def enter_homing(self, _):
        print("🔵 entering homing")
        self._maybe_fail_or_continue(3, Triggers.finished_homing, States.running.homing)

    def _maybe_fail_or_continue(self, delay, trigger_fn, expected_state):
        if self.simulate_failure:
            self.spawn(self._simulate_failure(delay, expected_state))
        else:
            self.spawn(self._delayed_trigger(delay, trigger_fn, expected_state))

    async def _delayed_trigger(self, delay, trigger_fn, expected_state):
        await asyncio.sleep(delay)
        print(f"⏱ Delay done. Current state: {self.state}, expected: {expected_state}")
        if self.state == str(expected_state):
            print(f"✅ Triggering: {trigger_fn}")
            self.trigger(trigger_fn())
        else:
            print("⛔ Skipping trigger due to unexpected state")

    async def _simulate_failure(self, delay, expected_state):
        await asyncio.sleep(delay)
        if self.state == str(expected_state):
            print(f"💥 Simulated failure in {self.state}")
            self.triggers.to_fault()
