"""
Configuration constants for the machine application.
Contains hardcoded base positions and application settings.
"""

# Base robot positions (hardcoded for safety)
# These are the known-good positions that users can fine-tune with offsets
BASE_PICK_POSITION = {
    "joint_angles": [0.0, -90.0, 90.0, 0.0, 90.0, 0.0],  # Joint angles in degrees
    "cartesian": {"x": 300.0, "y": 0.0, "z": 200.0}  # Cartesian position in mm
}

BASE_PLACE_POSITION = {
    "joint_angles": [180.0, -90.0, 90.0, 0.0, 90.0, 0.0],  # Joint angles in degrees
    "cartesian": {"x": -300.0, "y": 0.0, "z": 200.0}  # Cartesian position in mm
}

# Default hardware component names (can be overridden in Components model)
DEFAULT_COMPONENT_NAMES = {
    "robot": "Robot",
    "estop": "E-Stop",
    "box_sensor": "Box Sensor"
}

# Operation timeouts (in seconds)
TIMEOUTS = {
    "pick_operation": 10.0,
    "place_operation": 10.0,
    "wait_for_box": 30.0,
    "robot_movement": 15.0
}

# MQTT topics for state publishing
MQTT_TOPICS = {
    "state_change": "machine/state/change",
    "operation_status": "machine/operation/status",
    "error": "machine/error"
}

# Database configuration
DATABASE_URL = "sqlite:///./machine_app.db"

# API configuration
API_PORT = 3020
API_HOST = "0.0.0.0"
