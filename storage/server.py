from fastapi import FastAPI
from orchestrator import storage
from fastapi.responses import FileResponse

app = FastAPI()
storage.bootstrap(app)

@app.get("/")
def serve_index():
    return FileResponse("./static/index.html")

@app.get("/gripper-center/{id}")
def get_center(id: int):
    gripper = storage.gripper.get(id)
    if not gripper:
        return {"error": "Gripper not found"}
    return {"center": gripper.get_center_of_mass()}