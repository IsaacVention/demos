import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from app import CellFSM, STATES, TRANSITIONS

fsm = CellFSM(states=STATES, transitions=TRANSITIONS)
fsm.start()

app = FastAPI()


@app.get("/fsm/state")
def get_state():
    return {
        "state": fsm.state,
        "simulate_failure": fsm.simulate_failure,
        "recover_at_last_motion": fsm.recover_at_last_motion,
        "last_state": fsm.last_state,
    }


@app.post("/fsm/reset")
async def reset():
    fsm.reset()
    return JSONResponse(content={"result": "reset"})


@app.post("/fsm/start")
async def start():
    fsm.start()
    return {"result": "start"}


@app.post("/fsm/to_fault")
async def to_fault():
    fsm.to_fault()
    return JSONResponse(content={"result": "to_fault"})


@app.post("/fsm/set_simulate_failure")
def set_simulate_failure(flag: bool):
    fsm.simulate_failure = flag
    return JSONResponse(content={"simulate_failure": fsm.simulate_failure})


@app.post("/fsm/set_recover_last_motion")
def set_recover(flag: bool):
    fsm.recover_at_last_motion = flag
    return JSONResponse(content={"recover_at_last_motion": fsm.recover_at_last_motion})


@app.get("/")
def serve_index():
    return FileResponse("static/index.html")