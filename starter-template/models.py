from typing import Optional
from sqlmodel import SQLModel, Field

DEFAULT_ROBOT_REACH = 1750
DEFAULT_MAX_BOX_HEIGHT = 150
DEFAULT_TIMEOUT_SECONDS = 10

class Configuration(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    max_box_height: int = Field(default=DEFAULT_MAX_BOX_HEIGHT, description="Max height of a box in millimeters")
    timeout_seconds: int = Field(default=DEFAULT_TIMEOUT_SECONDS, description="Timeout in seconds for quiz answers")
    robot_reach: int = Field(default=DEFAULT_ROBOT_REACH, description="Robot reach in millimeters")

class Quiz(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    box_height: int
    num_boxes: int
    can_reach: Optional[bool] = None   # user-provided
    correct: Optional[bool] = None   # auto-evaluated after solution submitted