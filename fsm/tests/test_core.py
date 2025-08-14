import asyncio
import time
import unittest
from state_machine.core import StateMachine, TimeoutMixin, is_state_container
from state_machine.defs import State, StateGroup, Trigger


# ---------- helpers ---------------------------------------------------------


def make_empty_sm(**kwargs) -> StateMachine:
    """Return a bare machine (only ready/fault)."""
    return StateMachine(states=[], transitions=[], **kwargs)


class Duo(StateGroup):
    left: State = State()
    right: State = State()


class Container:
    g = Duo()


# ---------- TimeoutMixin ----------------------------------------------------


class TestTimeoutMixin(unittest.TestCase):
    def test_wrap_with_timeout(self):
        """_wrap_with_timeout should call set_timeout and return wrapped result."""

        class Dummy(TimeoutMixin):
            def set_timeout(self, s, sec, fn):
                self.called = (s, sec, fn())

        inst = Dummy()
        wrapped = inst._wrap_with_timeout(lambda v: f"ok:{v}", "S", 1, lambda: "T")
        self.assertEqual(wrapped("evt"), "ok:evt")
        self.assertEqual(inst.called, ("S", 1, "T"))


# ---------- defs.py ---------------------------------------------------------


class TestDefs(unittest.TestCase):
    def test_state_and_trigger(self):
        """State/Trigger naming, __repr__, __call__, and transition helper."""
        self.assertEqual(str(Duo.left), "Duo_left")
        self.assertRegex(repr(Duo.left), r"State\('Duo_left'\)")

        trig = Trigger("go")
        self.assertEqual(trig(), "go")
        self.assertRegex(repr(trig), r"Trigger\('go'\)")
        self.assertEqual(
            trig.transition("ready", Duo.left),
            {"trigger": "go", "source": "ready", "dest": "Duo_left"},
        )

    def test_state_group_list_and_validation(self):
        """StateGroup generates children list and raises on empty group."""
        self.assertEqual(Duo().to_state_list()[0]["initial"], "left")

        class Empty(StateGroup):
            pass

        with self.assertRaises(ValueError):
            Empty().to_state_list()


# ---------- core.py (sync) --------------------------------------------------


class TestCoreSync(unittest.TestCase):
    def test_is_state_container(self):
        """is_state_container returns True for StateGroup container, else False."""

        class NS:
            g = Duo()

        self.assertTrue(is_state_container(NS()))
        self.assertFalse(is_state_container(object()))

    def test_constructor_bad_states(self):
        """Passing invalid `states` arg raises TypeError."""

        class Foo:
            pass

        with self.assertRaises(TypeError):
            StateMachine(states=Foo(), transitions=[])

    def test_recovery_transitions_added(self):
        """Machine auto-adds recover__ transitions for all leaves."""
        sm = StateMachine(states=Container, transitions=[])
        self.assertTrue({"recover__Duo_left", "recover__Duo_right"} <= set(sm.events))

    def test_history_and_last_helpers(self):
        """history records transitions; last(n) slices correctly."""
        sm = make_empty_sm()
        sm.trigger("to_fault")
        self.assertEqual(sm.history[-1]["state"], "fault")
        self.assertEqual(sm.last(1), sm.history[-1:])


# ---------- core.py (async) -------------------------------------------------


class TestCoreAsync(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_branches(self):
        """Timeout fires when state unchanged; guard prevents when state mutated."""
        for mutate, expect in [(False, "fault"), (True, "interrupted")]:
            sm = make_empty_sm(enable_last_state_recovery=False)
            sm.set_timeout("ready", 0.02, lambda: "to_fault")
            if mutate:
                sm.state = "interrupted"
            await asyncio.sleep(0.03)
            self.assertEqual(sm.state, expect)

    async def test_spawn_and_cancel(self):
        """spawn tracks tasks and cancel_tasks() cancels them."""
        sm = make_empty_sm()

        async def sleeper():
            await asyncio.sleep(1)

        task = sm.spawn(sleeper())
        self.assertIn(task, sm._tasks)
        await sm.cancel_tasks()
        self.assertTrue(task.cancelled())

    async def test_record_history_duration(self):
        """_record_history_event adds duration_ms on second call."""
        sm = make_empty_sm()
        fake_evt = lambda d: type(
            "Evt", (), {"transition": type("T", (), {"dest": d})()}
        )
        sm._record_history_event(fake_evt("ready"))
        time.sleep(0.01)
        sm._record_history_event(fake_evt("fault"))
        self.assertIn("duration_ms", sm.history[0])

    async def test_misc_private_branches(self):
        """Covers _is_leaf, on_enter_ready(clear), clear_all_timeouts, start(recovery)."""
        sm = StateMachine(
            states=Container, transitions=[], enable_last_state_recovery=False
        )
        self.assertTrue(sm._is_leaf("Duo_left"))
        self.assertFalse(sm._is_leaf(type("X", (), {"children": [1]})()))
        sm._last_state = "X"
        sm.on_enter_ready(None)
        self.assertIsNone(sm._last_state)
        sm.set_timeout("ready", 0.1, lambda: "to_fault")
        sm._clear_all_timeouts()
        self.assertFalse(sm._timeouts)
        sm._enable_recovery, sm._last_state = True, "Duo_left"
        sm.start()
        self.assertEqual(sm.state, "Duo_left")


# ---------- core.py (edge cases) -------------------------------------------


class TestCoreEdgeCases(unittest.IsolatedAsyncioTestCase):
    def test_record_and_get_last_state(self):
        """record_last_state() stores current state; get_last_state() retrieves it."""
        sm = make_empty_sm()
        self.assertIsNone(sm.get_last_state())
        sm.state = "foo"
        sm.record_last_state()
        self.assertEqual(sm.get_last_state(), "foo")

    def test_start_else_branch(self):
        """start() follows normal transition path when recovery disabled."""
        sm = StateMachine(
            states=[{"name": "done"}],
            transitions=[{"trigger": "start", "source": "ready", "dest": "done"}],
            enable_last_state_recovery=False,
        )
        sm.start()
        self.assertEqual(sm.state, "done")

    def test_run_enter_callbacks(self):
        """_run_enter_callbacks iterates .enter list and calls handlers."""
        sm = make_empty_sm()
        hits = []
        sm.get_state("ready").enter = [lambda _: hits.append(True)]
        sm._run_enter_callbacks("ready")
        self.assertEqual(hits, [True])

    def test_on_enter_ready_both_paths(self):
        """on_enter_ready keeps or clears _last_state based on recovery flag."""
        for recover, expected in [(False, None), (True, "X")]:
            sm = make_empty_sm(enable_last_state_recovery=recover)
            sm._last_state = "X"
            sm.on_enter_ready(None)
            self.assertEqual(sm._last_state, expected)


if __name__ == "__main__":
    unittest.main()