# fsm_router.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import asyncio

def build_fsm_router(fsm, triggers=None):
    router = APIRouter()

    @router.get("/state")
    def get_state():
        return {
            "state": fsm.state,
            "last_state": fsm.get_last_state(),
        }

    if triggers is None:
        triggers = sorted(fsm.events.keys())

    for trigger_name in triggers:
        async def make_trigger(trigger=trigger_name):
            if not fsm.get_triggers(fsm.state) or trigger not in fsm.get_triggers(fsm.state):
                raise HTTPException(status_code=409, detail=f"Trigger {trigger} not allowed in {fsm.state}")
            method = getattr(fsm, trigger)
            result = method()
            if asyncio.iscoroutine(result):
                await result
            return JSONResponse(content={"result": trigger})
        
        router.add_api_route(
            f"/{trigger_name}",
            make_trigger,
            methods=["POST"],
            name=f"{trigger_name}_trigger",
        )

    return router