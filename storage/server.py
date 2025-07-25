from fastapi import FastAPI
from fastapi.responses import FileResponse
from orchestrator.accessor import ModelAccessor
from orchestrator.storage import bootstrap

from components.gripper.models import Gripper
from components.scanner.models import Scanner


# --------- BOOTSTRAP APP ---------
app = FastAPI()

grippers = ModelAccessor(Gripper, "gripper")
scanners = ModelAccessor(Scanner, "scanner")

bootstrap(
    app,
    models=[
        ("gripper", Gripper, grippers),
        ("scanner", Scanner, scanners),
    ],
)

# --------- ROUTES ---------
@app.get("/")
def serve_index():
    return FileResponse("./static/index.html")


@app.get("/gripper-center/{id}")
def get_center(id: int):
    gripper = grippers.get(id)
    if not gripper:
        return {"error": "Gripper not found"}
    return {"center": gripper.get_center_of_mass()}
