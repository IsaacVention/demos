from typing import Optional
from sqlmodel import Field, SQLModel


class JobRecipe(SQLModel, table=True):
    """Job recipe containing speed and position offsets for pick/place operations."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(description="Recipe name (e.g., 'Standard Pick/Place')")
    speed: float = Field(default=10.0, description="Robot speed in mm/s")
    
    pick_offset_x: float = Field(default=0.0, description="Pick position X offset in mm")
    pick_offset_y: float = Field(default=0.0, description="Pick position Y offset in mm")
    pick_offset_z: float = Field(default=0.0, description="Pick position Z offset in mm")
    
    place_offset_x: float = Field(default=0.0, description="Place position X offset in mm")
    place_offset_y: float = Field(default=0.0, description="Place position Y offset in mm")
    place_offset_z: float = Field(default=0.0, description="Place position Z offset in mm")


class Components(SQLModel, table=True):
    """Hardware component friendly names configuration."""
    id: Optional[int] = Field(default=None, primary_key=True)
    robot_name: str = Field(description="Friendly name of the robot in machine configuration")
    estop_name: str = Field(description="Friendly name of the E-Stop input in machine configuration")
    box_sensor_name: str = Field(description="Friendly name of the box sensor input in machine configuration")


class MachineState(SQLModel, table=True):
    """Current machine state for persistence and recovery."""
    id: Optional[int] = Field(default=None, primary_key=True)
    current_state: str = Field(description="Current state machine state")
    active_recipe_id: Optional[int] = Field(default=None, foreign_key="jobrecipe.id")
