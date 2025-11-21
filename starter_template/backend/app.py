"""
Quiz State Machine Implementation

This module contains the core state machine logic for the quiz application.
The state machine manages the flow of generating quiz problems, presenting them
to users, and grading their responses.
"""

import random
import asyncio
from state_machine.defs import StateGroup, State, Trigger
from state_machine.decorators import (
    on_enter_state,
    on_exit_state,
    auto_timeout,
    guard
)
from state_machine.core import StateMachine, BaseStates, BaseTriggers
from models import Quiz, Configuration, DEFAULT_MAX_BOX_HEIGHT, DEFAULT_TIMEOUT_SECONDS
from storage.accessor import ModelAccessor

MIN_BOX_HEIGHT = 100
MIN_NUM_BOXES = 7
MAX_NUM_BOXES = 20

# -------------------------------
# State Machine Definition
# -------------------------------

class QuizStates(StateGroup):
    """Sub states for the quiz state machine"""
    generating: State = State()  # Creating a new quiz problem
    presenting: State = State()  # Displaying the problem to the user
    grading: State = State()     # Waiting for and evaluating user response


class States:
    """Top level state machine states"""
    quiz = QuizStates()


class Triggers:
    """Events that trigger state transitions"""
    start = Trigger("start")
    problem_generated = Trigger("problem_generated")
    problem_presented = Trigger("problem_presented")
    answer_submitted = Trigger("answer_submitted")


# Define the allowed transitions between states
TRANSITIONS = [
    Triggers.start.transition(BaseStates.READY.value, States.quiz.generating),
    Triggers.problem_generated.transition(
        States.quiz.generating, States.quiz.presenting
    ),
    Triggers.problem_presented.transition(States.quiz.presenting, States.quiz.grading),
    Triggers.answer_submitted.transition(States.quiz.grading, States.quiz.generating),
]


# -------------------------------
# Quiz State Machine
# -------------------------------


class QuizMachine(StateMachine):
    """
    Quiz State Machine
    
    Manages the complete quiz workflow:
    1. Generating: Creates a new quiz problem with random parameters
    2. Presenting: Displays the problem to the user
    3. Grading: Waits for user response with configurable timeout
    4. Fault: Entered if timeout expires without correct answer
    
    The state machine automatically transitions between states based on
    user interactions and timeouts.
    """

    def __init__(
        self,
        quiz_accessor: ModelAccessor[Quiz],
        config_accessor: ModelAccessor[Configuration],
        *args,
        **kwargs,
    ):
        """Initialize the quiz state machine with data accessors"""
        kwargs.setdefault("states", States)
        kwargs.setdefault("transitions", TRANSITIONS)
        kwargs.setdefault("enable_last_state_recovery", False)
        super().__init__(*args, **kwargs)

        # Data accessors for quiz and configuration data
        self.quiz_accessor = quiz_accessor
        self.config_accessor = config_accessor
        
        # Internal state for timeout management
        self._grading_countdown_task = None
        self._current_time_remaining = None

    # ---------------------------
    # State Handlers
    # ---------------------------

    @on_enter_state(States.quiz.generating)
    @auto_timeout(1, Triggers.problem_generated)
    def enter_generating(self, _):
        """Generate a new quiz problem after a brief delay"""
        print("⚙️ Generating a new problem... (1s)")

    @on_enter_state(States.quiz.presenting)
    def enter_presenting(self, _):
        """Create and present a new quiz problem to the user"""
        # Get configuration settings
        config = self.config_accessor.get(1) if self.config_accessor else None
        max_box_height = config.max_box_height if config else DEFAULT_MAX_BOX_HEIGHT
        
        # Generate random problem parameters
        box_height = random.randint(MIN_BOX_HEIGHT, max_box_height)
        num_boxes = random.randint(MIN_NUM_BOXES, MAX_NUM_BOXES)

        # Store the new quiz problem
        self.quiz_accessor.insert(
            Quiz(box_height=box_height, num_boxes=num_boxes), actor="system"
        )

        # Move to grading state
        self.trigger(Triggers.problem_presented())

    @on_enter_state(States.quiz.grading)
    def enter_grading(self, _):
        """Start waiting for user response with configurable timeout"""
        # Get timeout configuration
        config = self.config_accessor.get(1) if self.config_accessor else None
        timeout_seconds = config.timeout_seconds if config else DEFAULT_TIMEOUT_SECONDS

        # Start countdown timer
        self._grading_countdown_task = self.spawn(self._countdown_task(timeout_seconds))

    @on_exit_state(States.quiz.grading)
    def exit_grading(self, _):
        """Clean up countdown task when leaving grading state"""
        if self._grading_countdown_task and not self._grading_countdown_task.done():
            self._grading_countdown_task.cancel()
            self._grading_countdown_task = None
        self._current_time_remaining = None

    async def _countdown_task(self, timeout_seconds: int):
        """Background task that counts down and triggers timeout if user doesn't respond"""
        for remaining in range(timeout_seconds, 0, -1):
            # Update time remaining for frontend polling
            self._current_time_remaining = remaining
            await asyncio.sleep(1)
        
        # Timeout reached - transition to fault state
        self._current_time_remaining = None
        self.trigger(BaseTriggers.TO_FAULT.value)

    # ---------------------------
    # State Transition Guards
    # ---------------------------

    @guard(Triggers.answer_submitted)
    def check_solution(self) -> bool:
        """Validate that the user's answer is correct before allowing state transition"""
        latest_quiz = self.quiz_accessor.all()[-1]
        return bool(latest_quiz.correct)