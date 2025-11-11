"""
FastAPI Server for Quiz Application

This module sets up the FastAPI server with all necessary endpoints
for the quiz application, including state machine management and data access.
"""


from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.vention_communication.app import VentionApp
from src.vention_communication.decorators import stream
from vention_storage.src.storage.accessor import ModelAccessor
from vention_storage.src.storage.bootstrap import bootstrap
from vention_storage.src.storage.vention_communication import build_storage_bundle
from vention_state_machine.src.state_machine.vention_communication import build_state_machine_bundle

from demo_server.app import QuizMachine
from demo_server.models import Configuration, Quiz, DEFAULT_ROBOT_REACH, DEFAULT_MAX_BOX_HEIGHT, DEFAULT_TIMEOUT_SECONDS

# -------------------------------
# Server Application Setup
# -------------------------------
app = VentionApp(title="Machine Code Demo - Quiz Application", emit_proto=True)

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

@stream(name="state_change", payload=StateChangeEvent, queue_maxsize=10, replay=True, policy="fifo")
async def publish_state_change(old_state: str, new_state: str, trigger: str) -> StateChangeEvent:
    return StateChangeEvent(old_state=old_state, new_state=new_state, trigger=trigger)

# -------------------------------
# State Machine Initialization
# -------------------------------

# Create and configure the quiz state machine
quiz_machine = QuizMachine(
    quiz_accessor,
    config_accessor,
    publish_state_change
)

# Include state machine router for all state machine operations
app.register_rpc_plugin(build_state_machine_bundle(quiz_machine))
app.register_rpc_plugin(build_storage_bundle(accessors=[quiz_accessor, config_accessor]))
app.finalize()