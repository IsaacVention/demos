# server.py
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app import CellFSM, STATES, TRANSITIONS
from fastapi.responses import FileResponse
from fsm_router import build_fsm_router

fsm = CellFSM(states=STATES, transitions=TRANSITIONS)

fsm.start()

app = FastAPI()
fsm_router = build_fsm_router(fsm)
app.include_router(fsm_router, prefix="/fsm")

@app.post("/fsm/set_simulate_failure")
def set_simulate_failure(flag: bool):
    fsm.simulate_failure = flag
    return JSONResponse(content={"simulate_failure": fsm.simulate_failure})

@app.post("/fsm/set_recover_last_motion")
def set_recover_last_motion(flag: bool):
    fsm._enable_recovery = flag
    return JSONResponse(content={"recover_last_motion": fsm._enable_recovery})

@app.get("/")
def serve_index():
    return FileResponse("static/index.html")