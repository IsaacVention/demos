import asyncio
import signal
import sys
from app import CellFSM, STATES, TRANSITIONS, attach_logging

async def main():
    fsm = CellFSM(states=STATES, transitions=TRANSITIONS)
    attach_logging(fsm)
    fsm.start()
    
    async def estop_in_3s():
        await asyncio.sleep(3)
        print("🚨 Incoming ESTOP (to_fault)!")
        fsm.to_fault()

    # Uncomment this to simulate estop after 3s (bubbling down)
    # asyncio.create_task(estop_in_3s())

    while True:
        await asyncio.sleep(1)

for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, lambda *_: sys.exit(0))

asyncio.run(main())