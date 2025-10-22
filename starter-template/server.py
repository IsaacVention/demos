from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from storage.accessor import ModelAccessor
from storage.bootstrap import bootstrap
from state_machine.router import build_router

from app import QuizMachine
from models import Configuration, Quiz, DEFAULT_ROBOT_REACH, DEFAULT_MAX_BOX_HEIGHT, DEFAULT_TIMEOUT_SECONDS

# -------------------------------
# FastAPI Setup
# -------------------------------

app = FastAPI(title="Starter Template - Quiz Demo")

# -------------------------------
# Storage
# -------------------------------


quiz_accessor = ModelAccessor(Quiz, "quiz")
config_accessor = ModelAccessor(Configuration, "config")

bootstrap(app, accessors=[quiz_accessor, config_accessor])

# Populate config if empty
if not config_accessor.all():
    config_accessor.insert(Configuration(
        max_box_height=DEFAULT_MAX_BOX_HEIGHT,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        robot_reach=DEFAULT_ROBOT_REACH,
    ), actor="system")


# Check if incoming solution is correct
@quiz_accessor.before_update()
def before_update_hook(_, instance: Quiz):
    print(f"Before update hook: {instance}")
    if instance.can_reach is not None:
        robot_reach = config_accessor.get(1).robot_reach if config_accessor.get(1) else 1750
        print(f"Robot reach: {robot_reach}")
        print(f"Box height: {instance.box_height}")
        print(f"Number of boxes: {instance.num_boxes}")
        correct_solution = (instance.box_height * instance.num_boxes) <= robot_reach
        print(f"Correct solution: {correct_solution}")
        instance.correct = correct_solution == instance.can_reach

# -------------------------------
# WebSocket Clients
# -------------------------------

state_clients: set[WebSocket] = set()


@app.websocket("/ws/state")
async def ws_state(websocket: WebSocket):
    await websocket.accept()
    state_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state_clients.remove(websocket)


# -------------------------------
# Publishers
# -------------------------------


async def broadcast_state(old: str, new: str, trigger: str, time_remaining: int):
    msg = {"old": old, "new": new, "trigger": trigger, "time_remaining": time_remaining}
    dead = []
    for websocket in list(state_clients):
        try:
            await websocket.send_json(msg)
        except Exception:
            dead.append(websocket)
    for dead_websocket in dead:
        state_clients.remove(dead_websocket)



# -------------------------------
# State Machine Setup
# -------------------------------

quiz_machine = QuizMachine(
    quiz_accessor,
    config_accessor,
    publish_state=broadcast_state,
)

app.include_router(build_router(quiz_machine), prefix="/server")