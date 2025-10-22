import random
import asyncio
from typing import Callable, Optional
from state_machine.defs import StateGroup, State, Trigger
from state_machine.decorators import (
    on_enter_state,
    on_exit_state,
    auto_timeout,
    guard,
    on_state_change,
)
from state_machine.core import StateMachine, BaseStates, BaseTriggers
from models import Quiz, Configuration, DEFAULT_MAX_BOX_HEIGHT, DEFAULT_TIMEOUT_SECONDS
from storage.accessor import ModelAccessor

MIN_BOX_HEIGHT = 100
MIN_NUM_BOXES = 7
MAX_NUM_BOXES = 20

# -------------------------------
# State & Trigger Declarations
# -------------------------------


class QuizStates(StateGroup):
    generating: State = State()
    presenting: State = State()
    grading: State = State()


class States:
    quiz = QuizStates()


class Triggers:
    start = Trigger("start")
    problem_generated = Trigger("problem_generated")
    problem_presented = Trigger("problem_presented")
    answer_submitted = Trigger("answer_submitted")


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
    A quiz state machine with three states:
    - Generating: wait 3s, create a new problem
    - Presenting: briefly show problem (UI can display it)
    - Grading: wait for user input; retries allowed
    - Fault: entered if timeout expires without correct answer
    """

    def __init__(
        self,
        quiz_accessor: ModelAccessor[Quiz],
        config_accessor: ModelAccessor[Configuration],
        publish_state: Optional[Callable[[str, str, str, int], None]] = None,
        publish_quiz: Optional[Callable[[Quiz], None]] = None,
        *args,
        **kwargs,
    ):
        kwargs.setdefault("states", States)
        kwargs.setdefault("transitions", TRANSITIONS)
        kwargs.setdefault("enable_last_state_recovery", False)
        super().__init__(*args, **kwargs)

        self.quiz_accessor = quiz_accessor
        self.config_accessor = config_accessor
        self.publish_state = publish_state
        self.publish_quiz = publish_quiz
        self._grading_countdown_task = None

    # ---------------------------
    # State Handlers
    # ---------------------------

    @on_enter_state(States.quiz.generating)
    @auto_timeout(1, Triggers.problem_generated)
    def enter_generating(self, _):
        """Simulate thinking time for problem generation."""
        print("⚙️ Generating a new problem... (1s)")

    @on_enter_state(States.quiz.presenting)
    def enter_presenting(self, _):
        config = self.config_accessor.get(1) if self.config_accessor else None
        max_box_height = config.max_box_height if config else DEFAULT_MAX_BOX_HEIGHT
        box_height = random.randint(MIN_BOX_HEIGHT, max_box_height)
        num_boxes = random.randint(MIN_NUM_BOXES, MAX_NUM_BOXES)

        quiz = self.quiz_accessor.insert(
            Quiz(box_height=box_height, num_boxes=num_boxes), actor="system"
        )

        if self.publish_quiz:
            self.spawn(self.publish_quiz(quiz))

        self.trigger(Triggers.problem_presented())

    @on_enter_state(States.quiz.grading)
    def enter_grading(self, _):
        """Wait for user answer with configurable timeout and countdown."""
        config = self.config_accessor.get(1) if self.config_accessor else None
        timeout_seconds = config.timeout_seconds if config else DEFAULT_TIMEOUT_SECONDS

        # Start new countdown task
        self._grading_countdown_task = self.spawn(self._countdown_task(timeout_seconds))

    @on_exit_state(States.quiz.grading)
    def exit_grading(self, _):
        """Cancel countdown task when leaving grading state."""
        if self._grading_countdown_task and not self._grading_countdown_task.done():
            self._grading_countdown_task.cancel()
            self._grading_countdown_task = None

    async def _countdown_task(self, timeout_seconds: int):
        """Countdown task that publishes time remaining and triggers timeout."""
        for remaining in range(timeout_seconds, 0, -1):
            if self.publish_state:
                self.spawn(
                    self.publish_state(
                        str(States.quiz.grading),
                        str(States.quiz.grading),
                        "countdown",
                        remaining,
                    )
                )
            await asyncio.sleep(1)
        self.trigger(BaseTriggers.TO_FAULT.value)

    # ---------------------------
    # Guards
    # ---------------------------

    @guard(Triggers.answer_submitted)
    def check_solution(self) -> bool:
        """Only allow transition if latest answer is correct."""
        latest = self.quiz_accessor.all()[-1]
        return bool(latest.correct)

    # ---------------------------
    # State Change Callback
    # ---------------------------

    @on_state_change
    def handle_state_change(self, old_state: str, new_state: str, trigger: str):
        """Called on every state change."""
        if self.publish_state:
            self.spawn(self.publish_state(old_state, new_state, trigger, -1))
