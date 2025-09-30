from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

from models import JobRecipe, Components, MachineState
from config import API_PORT, API_HOST, DATABASE_URL
from storage.bootstrap import bootstrap
from storage.accessor import ModelAccessor
from pick_place_machine import PickPlaceMachine
from state_machine.router import build_router

# Initialize FastAPI app
app = FastAPI(
    title="Starter Template API",
    description="API for machine control and configuration",
    version="1.0.0"
)

# Add CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize accessors
job_recipe_accessor = ModelAccessor(JobRecipe, "job_recipe")
components_accessor = ModelAccessor(Components, "components")
machine_state_accessor = ModelAccessor(MachineState, "machine_state")

# Bootstrap storage system
bootstrap(
    app,
    accessors=[job_recipe_accessor, components_accessor, machine_state_accessor],
    database_url=DATABASE_URL,
    create_tables=True,
    enable_db_router=True
)

machine = PickPlaceMachine()

fsm_router = build_router(machine)
app.include_router(fsm_router, prefix="/machine")

# Pydantic models for request/response
class StartRequest(BaseModel):
    jobId: int

class OperationResponse(BaseModel):
    status: str
    message: str

class StatusResponse(BaseModel):
    current_state: str
    is_running: bool
    active_recipe: Optional[dict] = None

# Global machine controller reference (will be set by state machine process)
machine_controller = None

def set_machine_controller(controller):
    """Set the machine controller reference from the state machine process."""
    global machine_controller
    machine_controller = controller

# Operation Control Endpoints
@app.post("/operation/start", response_model=OperationResponse)
async def start_operation(request: StartRequest):
    """Start machine operation with specified job recipe."""
    try:
        # Load the job recipe
        recipe = job_recipe_accessor.get(request.jobId)
        if not recipe:
            raise HTTPException(status_code=404, detail=f"Job recipe with ID {request.jobId} not found")
        
        # Update machine state with active recipe
        machine_state = machine_state_accessor.get(1)  # Single state record
        if machine_state:
            machine_state.active_recipe_id = request.jobId
            machine_state_accessor.save(machine_state, actor="api")
        else:
            machine_state_accessor.insert(
                MachineState(current_state="ready", active_recipe_id=request.jobId), 
                actor="api"
            )
        
        # Start the machine controller if available
        if machine_controller:
            machine_controller.start_operation(recipe)
        
        return OperationResponse(
            status="success",
            message=f"Operation started with recipe: {recipe.name}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/operation/stop", response_model=OperationResponse)
async def stop_operation():
    """Stop machine operation."""
    try:
        if machine_controller:
            machine_controller.stop_operation()
        
        return OperationResponse(
            status="success",
            message="Operation stopped"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/operation/reset", response_model=OperationResponse)
async def reset_operation():
    """Reset machine from fault state."""
    try:
        if machine_controller:
            machine_controller.reset_operation()
        
        return OperationResponse(
            status="success",
            message="Machine reset from fault state"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/operation/status", response_model=StatusResponse)
async def get_operation_status():
    """Get current machine operation status."""
    try:
        # Get current machine state
        machine_state = machine_state_accessor.get(1)
        current_state = machine_state.current_state if machine_state else "ready"
        is_running = current_state not in ["ready", "fault"]
        
        # Get active recipe info if available
        active_recipe = None
        if machine_state and machine_state.active_recipe_id:
            recipe = job_recipe_accessor.get(machine_state.active_recipe_id)
            if recipe:
                active_recipe = {
                    "id": recipe.id,
                    "name": recipe.name,
                    "speed": recipe.speed,
                    "pick_offset": {
                        "x": recipe.pick_offset_x,
                        "y": recipe.pick_offset_y,
                        "z": recipe.pick_offset_z
                    },
                    "place_offset": {
                        "x": recipe.place_offset_x,
                        "y": recipe.place_offset_y,
                        "z": recipe.place_offset_z
                    }
                }
        
        return StatusResponse(
            current_state=current_state,
            is_running=is_running,
            active_recipe=active_recipe
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Configuration Endpoints
@app.get("/config/components")
async def get_components():
    """Get hardware component configuration."""
    try:
        components = components_accessor.all()
        if not components:
            # Return default component names if none configured
            from config import DEFAULT_COMPONENT_NAMES
            return {
                "robot_name": DEFAULT_COMPONENT_NAMES["robot"],
                "estop_name": DEFAULT_COMPONENT_NAMES["estop"],
                "box_sensor_name": DEFAULT_COMPONENT_NAMES["box_sensor"]
            }
        
        component = components[0]  # Single component configuration
        return {
            "robot_name": component.robot_name,
            "estop_name": component.estop_name,
            "box_sensor_name": component.box_sensor_name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/config/components")
async def update_components(components_data: dict):
    """Update hardware component configuration."""
    try:
        # Get existing components or create new
        components = components_accessor.all()
        if components:
            component = components[0]
            component.robot_name = components_data["robot_name"]
            component.estop_name = components_data["estop_name"]
            component.box_sensor_name = components_data["box_sensor_name"]
            components_accessor.save(component, actor="api")
        else:
            components_accessor.insert(
                Components(
                    robot_name=components_data["robot_name"],
                    estop_name=components_data["estop_name"],
                    box_sensor_name=components_data["box_sensor_name"]
                ),
                actor="api"
            )
        
        return {"status": "success", "message": "Components configuration updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "machine-code-demo-api"}

if __name__ == "__main__":
    uvicorn.run(app, host=API_HOST, port=API_PORT)
