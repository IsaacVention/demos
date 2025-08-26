from fastapi import FastAPI
from fastapi.responses import FileResponse
from storage.accessor import ModelAccessor
from storage.bootstrap import bootstrap

from components.gripper.models import Gripper
from components.scanner.models import Scanner


# --------- BOOTSTRAP APP ---------
app = FastAPI()

# Wrap SQLModel classes with ModelAccessor for easy access
grippers = ModelAccessor(Gripper, "gripper")
scanners = ModelAccessor(Scanner, "scanner")

# Create DB, serve rest endpoints

bootstrap(app, accessors=[grippers, scanners])

@grippers.before_update()
def before_gripper_update(session, instance: Gripper):
   if instance.length < 0:
       raise ValueError("Gripper length cannot be negative")

# --------- ROUTES ---------
@app.get("/")
def serve_index():
    return FileResponse("./static/index.html")

@app.get("/gripper-center/{id}")
def get_center(id: int):
    # Example returning pythonic class instance from db get
    gripper = grippers.get(id)
    if not gripper:
        return {"error": "Gripper not found"}
    return {"center": gripper.get_center_of_mass()}

def accessor_examples():
    # pythonic list operations on sql data
    longGripper = filter(lambda g: g.length > 10, grippers.all())
    
    # accessing/mutating single entry
    gripper = grippers.get(1)
    gripper.length = 10
    grippers.save(gripper)
    
    # deleting an entry
    grippers.delete(1)
    
