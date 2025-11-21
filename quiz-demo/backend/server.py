"""
FastAPI Server for Quiz Application

This module sets up the FastAPI server with all necessary endpoints
for the quiz application, including state machine management and data access.
"""


import subprocess
import threading
from pathlib import Path
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from communication.app import VentionApp
from communication.decorators import stream, action
from storage.accessor import ModelAccessor
from storage.bootstrap import bootstrap
from storage.vention_communication import build_storage_bundle
from state_machine.vention_communication import build_state_machine_bundle

from app import QuizMachine
from models import Configuration, Quiz, DEFAULT_ROBOT_REACH, DEFAULT_MAX_BOX_HEIGHT, DEFAULT_TIMEOUT_SECONDS

# -------------------------------
# Server Application Setup
# -------------------------------
app = VentionApp(title="Machine Code Demo - Quiz Application", emit_proto=True, proto_path="../src/app/gen/app.proto")

# Configure CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class StateChangeEvent(BaseModel):
    old_state: str
    new_state: str
    trigger: str
    time_remaining: Optional[int] = None
    
class CountdownEvent(BaseModel):
    time_remaining: int

# -------------------------------
# Database Setup and Data Access
# -------------------------------

# Create data accessors for quiz and configuration data
quiz_accessor = ModelAccessor(Quiz, "quiz")
config_accessor = ModelAccessor(Configuration, "config")

# Initialize database with accessors
bootstrap()

# Initialize default configuration if none exists
if not config_accessor.all():
    config_accessor.insert(Configuration(
        max_box_height=DEFAULT_MAX_BOX_HEIGHT,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        robot_reach=DEFAULT_ROBOT_REACH,
    ), actor="system")


# -------------------------------
# Data Validation and Business Logic
# -------------------------------

@quiz_accessor.before_update()
def validate_quiz_answer(_, instance: Quiz):
    """
    Automatically validate user answers when quiz data is updated.
    
    This hook runs before any quiz record is updated and calculates
    whether the user's answer is correct based on robot reach constraints.
    """
    print(f"Validating quiz answer: {instance}")
    
    if instance.can_reach is not None:
        # Get robot reach from configuration
        robot_reach = config_accessor.get(1).robot_reach if config_accessor.get(1) else DEFAULT_ROBOT_REACH
        
        # Calculate the correct answer based on robot constraints
        total_height = instance.box_height * instance.num_boxes
        correct_solution = total_height <= robot_reach
        
        # Set the correctness flag
        instance.correct = correct_solution == instance.can_reach

# -------------------------------
# API Endpoints
# -------------------------------


class SimonResponse(BaseModel):
    message: str


@action()
async def simon_say_hello() -> SimonResponse:
    return SimonResponse(message="Yo wassup")

@stream(name="state_change", payload=StateChangeEvent, queue_maxsize=10, replay=True, policy="fifo")
async def publish_state_change(old_state: str, new_state: str, trigger: str) -> StateChangeEvent:
    return StateChangeEvent(old_state=old_state, new_state=new_state, trigger=trigger)

@stream(name="countdown", payload=CountdownEvent, queue_maxsize=10, replay=True)
async def publish_countdown(time_remaining: int) -> CountdownEvent:
    return CountdownEvent(time_remaining=time_remaining)

# -------------------------------
# State Machine Initialization
# -------------------------------

# Create and configure the quiz state machine
quiz_machine = QuizMachine(
    quiz_accessor,
    config_accessor,
    publish_state_change,
    publish_countdown
)

# Include state machine router for all state machine operations
app.register_rpc_plugin(build_state_machine_bundle(quiz_machine))
app.register_rpc_plugin(build_storage_bundle(accessors=[quiz_accessor, config_accessor]))
app.finalize()

# Generate TypeScript code from the proto file
def generate_typescript_from_proto():
    """Generate TypeScript code from the proto file using buf."""
    try:
        # Get the path to the frontend directory (src/)
        backend_dir = Path(__file__).parent
        frontend_dir = backend_dir.parent / "src"
        
        if not frontend_dir.exists():
            print(f"Warning: Frontend directory not found at {frontend_dir}")
            return
        
        # Change to frontend directory and run the generate script
        result = subprocess.run(
            ["npm", "run", "generate:proto"],
            cwd=str(frontend_dir),
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            print("✓ Successfully generated TypeScript code from proto file")
        else:
            print(f"Warning: Failed to generate TypeScript code: {result.stderr}")
    except Exception as e:
        print(f"Warning: Could not generate TypeScript code: {e}")

# Run code generation in a background thread to avoid blocking server startup
print("Starting TypeScript code generation in background...")
threading.Thread(target=generate_typescript_from_proto, daemon=True).start()