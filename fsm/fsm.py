import asyncio
from transitions.extensions.asyncio import HierarchicalMachine as HSM

class FoundationFSM(HSM):
    """
    Base FSM with safety shell and task cancellation.
    """
    def __init__(self, *args, states=None, **kw):
        super().__init__(
            states=(states or []) + ['ready', 'fault'],
            initial='ready',
            send_event=True,
            **kw
        )
        self.add_transition('to_fault', '*', 'fault', before='cancel_tasks')
        self.add_transition('reset', 'fault', 'ready')
        self._tasks: set[asyncio.Task] = set()

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