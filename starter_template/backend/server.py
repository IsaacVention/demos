"""
FastAPI Server for Quiz Application

This module sets up the FastAPI server with all necessary endpoints
for the quiz application, including state machine management and data access.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from storage.accessor import ModelAccessor
from storage.bootstrap import bootstrap
from state_machine.router import build_router

from app import QuizMachine
from models import Configuration, Quiz, DEFAULT_ROBOT_REACH, DEFAULT_MAX_BOX_HEIGHT, DEFAULT_TIMEOUT_SECONDS

# -------------------------------
# FastAPI Application Setup
# -------------------------------

app = FastAPI(
    title="Machine Code Demo - Quiz Application",
    description="A demonstration of the Machine Code Developer Toolkit featuring a quiz application with state machine management"
)

# Configure CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# Database Setup and Data Access
# -------------------------------

# Create data accessors for quiz and configuration data
quiz_accessor = ModelAccessor(Quiz, "quiz")
config_accessor = ModelAccessor(Configuration, "config")

# Initialize database with accessors
bootstrap(app, accessors=[quiz_accessor, config_accessor])

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
# State Machine Initialization
# -------------------------------

# Create and configure the quiz state machine
quiz_machine = QuizMachine(
    quiz_accessor,
    config_accessor
)

# -------------------------------
# API Endpoints
# -------------------------------

@app.get("/server/state")
async def get_application_state():
    """
    Get the current state of the quiz application.
    
    Returns the current state machine state and time remaining
    for the current quiz question (if applicable).
    """
    state = quiz_machine.state
    time_remaining = None
    
    # Get time remaining from countdown task if in grading state
    if hasattr(quiz_machine, '_grading_countdown_task') and quiz_machine._grading_countdown_task:
        if hasattr(quiz_machine, '_current_time_remaining'):
            time_remaining = quiz_machine._current_time_remaining
    
    return {
        "state": state,
        "time_remaining": time_remaining
    }

# Include state machine router for all state machine operations
app.include_router(build_router(quiz_machine), prefix="/server")