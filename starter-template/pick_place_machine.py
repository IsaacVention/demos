from state_machine.core import StateMachine, BaseStates
from state_machine.defs import StateGroup, State, Trigger
from state_machine.decorators import (
    on_enter_state,
    auto_timeout,
    guard,
    on_state_change,
)
from storage.accessor import ModelAccessor
from models import JobRecipe, Components, MachineState
from config import TIMEOUTS
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Define States using the DSL
class OperationStates(StateGroup):
    homing: State = State()
    waitingForBox: State = State()
    picking: State = State()
    placing: State = State()


class States:
    operation = OperationStates()


# Define Triggers
class Triggers:
    start = Trigger("start")
    home_complete = Trigger("home_complete")
    box_detected = Trigger("box_detected")
    pick_complete = Trigger("pick_complete")
    place_complete = Trigger("place_complete")
    stop = Trigger("stop")
    home = Trigger("home")
    to_fault = Trigger("to_fault")
    reset = Trigger("reset")


# Define Transitions
TRANSITIONS = [
    # Start sequence
    Triggers.start.transition(BaseStates.READY.value, States.operation.homing),
    Triggers.home_complete.transition(
        States.operation.homing, States.operation.waitingForBox
    ),
    # Main operation loop
    Triggers.box_detected.transition(
        States.operation.waitingForBox, States.operation.picking
    ),
    Triggers.pick_complete.transition(
        States.operation.picking, States.operation.placing
    ),
    Triggers.place_complete.transition(
        States.operation.placing, States.operation.waitingForBox
    ),
    # Stop/Home commands
    Triggers.stop.transition(States.operation.waitingForBox, States.operation.homing),
    Triggers.stop.transition(States.operation.picking, States.operation.homing),
    Triggers.stop.transition(States.operation.placing, States.operation.homing),
    Triggers.home.transition(States.operation.waitingForBox, States.operation.homing),
    Triggers.home.transition(States.operation.picking, States.operation.homing),
    Triggers.home.transition(States.operation.placing, States.operation.homing),
    # Fault transitions (global)
    Triggers.to_fault.transition(States.operation.homing, "fault"),
    Triggers.to_fault.transition(States.operation.waitingForBox, "fault"),
    Triggers.to_fault.transition(States.operation.picking, "fault"),
    Triggers.to_fault.transition(States.operation.placing, "fault"),
]


class PickPlaceMachine(StateMachine):
    """Pick and Place State Machine - demonstrates vention-state-machine power."""

    def __init__(self):
        super().__init__(
            states=States,
            transitions=TRANSITIONS,
            enable_last_state_recovery=True,  # Resume from last state on restart
        )

        # Initialize storage accessors
        self.job_recipe_accessor = ModelAccessor(JobRecipe, "job_recipe")
        self.components_accessor = ModelAccessor(Components, "components")
        self.machine_state_accessor = ModelAccessor(MachineState, "machine_state")

        # Runtime state
        self.active_recipe = None
        self.components_config = None
        self.estop_pressed = False
        self.box_sensor_high = False

    # State Entry Handlers - minimal, focused logic
    @on_enter_state(States.operation.homing)
    @auto_timeout(TIMEOUTS["robot_movement"], Triggers.to_fault)
    def enter_homing(self, _):
        """Home the robot to safe position."""
        logger.info("🔺 Homing robot to safe position")
        # TODO: Implement robot homing movement
        # - Move robot to safe home position
        # - Verify robot reached home
        # - Trigger home_complete when done

    @on_enter_state(States.operation.waitingForBox)
    @auto_timeout(TIMEOUTS["wait_for_box"], Triggers.to_fault)
    def enter_waitingForBox(self, _):
        """Wait for box sensor to go high."""
        logger.info("⏳ Waiting for box sensor to go high")
        # TODO: Implement box sensor monitoring
        # - Monitor box sensor input
        # - Trigger box_detected when sensor goes high
        # - Handle timeout if no box detected

    @on_enter_state(States.operation.picking)
    @auto_timeout(TIMEOUTS["pick_operation"], Triggers.to_fault)
    def enter_picking(self, _):
        """Execute pick operation."""
        logger.info("🔹 Executing pick operation")
        # TODO: Implement pick operation
        # - Move to pick position (base + offsets from recipe)
        # - Execute pick motion (gripper close, etc.)
        # - Verify pick success
        # - Trigger pick_complete when done

    @on_enter_state(States.operation.placing)
    @auto_timeout(TIMEOUTS["place_operation"], Triggers.to_fault)
    def enter_placing(self, _):
        """Execute place operation."""
        logger.info("🔸 Executing place operation")
        # TODO: Implement place operation
        # - Move to place position (base + offsets from recipe)
        # - Execute place motion (gripper open, etc.)
        # - Verify place success
        # - Check box sensor state
        # - Trigger place_complete when done

    # Guard Conditions - safety and validation
    @guard(Triggers.start)
    def validate_recipe_exists(self) -> bool:
        """Ensure we have a valid recipe before starting."""
        try:
            # Get active recipe from machine state
            machine_states = self.machine_state_accessor.all()
            if not machine_states or not machine_states[0].active_recipe_id:
                logger.error("❌ No active recipe configured")
                return False

            # Validate recipe exists
            recipe = self.job_recipe_accessor.get(
                machine_states[0].active_recipe_id
            )
            if not recipe:
                logger.error("❌ Active recipe not found")
                return False

            self.active_recipe = recipe
            logger.info(f"✅ Using recipe: {recipe.name}")
            return True

        except Exception as e:
            logger.error(f"❌ Recipe validation failed: {e}")
            return False

    @guard(Triggers.reset)
    def check_estop_released(self) -> bool:
        """Only allow reset when E-Stop is released."""
        return not self.estop_pressed

    # Global State Change Callback - MQTT publishing
    @on_state_change
    def publish_state_to_mqtt(self, old_state: str, new_state: str, trigger: str):
        """Publish state changes to MQTT for frontend display."""
        logger.info(f"📡 State change: {old_state} → {new_state} (trigger: {trigger})")
        # TODO: Implement MQTT publishing
        # - Publish state change to MQTT_TOPICS["state_change"]
        # - Include old_state, new_state, trigger, timestamp
        # - Include active recipe info if available

    # External Event Handlers - called by robot/sensor systems
    def on_estop_pressed(self):
        """Handle E-Stop pressed event."""
        self.estop_pressed = True
        self.trigger(Triggers.to_fault.value)

    def on_estop_released(self):
        """Handle E-Stop released event."""
        self.estop_pressed = False

    def on_box_sensor_high(self):
        """Handle box sensor going high."""
        self.box_sensor_high = True
        if self.state == States.operation.waitingForBox.value:
            self.trigger(Triggers.box_detected.value)

    def on_box_sensor_low(self):
        """Handle box sensor going low."""
        self.box_sensor_high = False

    def on_robot_home_complete(self):
        """Handle robot homing complete."""
        self.trigger(Triggers.home_complete.value)

    def on_robot_pick_complete(self):
        """Handle robot pick operation complete."""
        self.trigger(Triggers.pick_complete.value)

    def on_robot_place_complete(self):
        """Handle robot place operation complete."""
        # Check box sensor state to determine next action
        if self.box_sensor_high:
            # Box still present, go directly to picking
            self.trigger(Triggers.box_detected.value)
        else:
            # No box, go to waiting
            self.trigger(Triggers.place_complete.value)


# Global instance for the application
machine = PickPlaceMachine()


def get_machine() -> PickPlaceMachine:
    """Get the global state machine instance."""
    return machine
