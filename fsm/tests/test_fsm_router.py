import pytest
import asyncio

from fsm import (
    FoundationFSM,
    on_enter_state,
    on_exit_state,
    auto_timeout,
)


@pytest.mark.asyncio
async def test_basic_lifecycle(simple_fsm):
    assert simple_fsm.state == "ready"
    simple_fsm.start()
    assert simple_fsm.state == "foo"

    hist = simple_fsm.history
    assert hist[-1]["state"] == "foo"
    assert "timestamp" in hist[-1]

    simple_fsm.trigger("reset")
    assert simple_fsm.state == "ready"

    last1 = simple_fsm.last(1)
    assert last1 == hist[-1:]


@pytest.mark.asyncio
async def test_decorator_hooks_and_timeouts():
    calls = []

    class MyFSM(FoundationFSM):
        @on_enter_state("bar")
        @auto_timeout(0.01, "to_fault")
        def enter_bar(self, _):
            calls.append("enter_bar")

        @on_exit_state("bar")
        def exit_bar(self, _):
            calls.append("exit_bar")

    fsm = MyFSM(
        states=[{"name": "bar"}],
        transitions=[{"trigger": "start", "source": "ready", "dest": "bar"}],
    )
    fsm.start()
    assert calls == ["enter_bar"]

    # wait past timeout
    await asyncio.sleep(0.02)
    assert fsm.state == "fault"
    assert "exit_bar" in calls


@pytest.mark.asyncio
async def test_spawn_and_cancel():
    class CancelFSM(FoundationFSM):
        pass

    fsm = CancelFSM(
        states=["foo"],
        transitions=[
            {"trigger": "start", "source": "ready", "dest": "foo"},
            {
                "trigger": "to_fault",
                "source": "*",
                "dest": "fault",
                "before": "cancel_tasks",
            },
        ],
    )

    cancelled = False

    async def long_task():
        nonlocal cancelled
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled = True

    task = fsm.spawn(long_task())
    fsm.trigger("to_fault")
    await asyncio.sleep(0)  # let cancellation propagate
    assert cancelled is True


def test_history_buffer_limit():
    fsm = FoundationFSM(
        states=["s1", "s2"],
        transitions=[
            {"trigger": "t1", "source": "ready", "dest": "s1"},
            {"trigger": "t2", "source": "s1", "dest": "s2"},
            {"trigger": "t3", "source": "s2", "dest": "ready"},
        ],
        history_size=2,
    )
    fsm.start()
    fsm.trigger("t2")
    fsm.trigger("t3")
    assert len(fsm.history) == 2


@pytest.mark.asyncio
async def test_recovery():
    class RecFSM(FoundationFSM):
        pass

    fsm1 = RecFSM(
        states=["bar"],
        transitions=[{"trigger": "start", "source": "ready", "dest": "bar"}],
        enable_last_state_recovery=True,
    )
    fsm1.start()
    assert fsm1.state == "bar"

    fsm2 = RecFSM(
        states=["bar"],
        transitions=[{"trigger": "start", "source": "ready", "dest": "bar"}],
        enable_last_state_recovery=True,
    )
    # copy last state and start
    fsm2._last_state = fsm1._last_state
    fsm2.start()
    assert fsm2.state == "bar"
