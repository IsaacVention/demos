"""
Data Models for Quiz Application

This module defines the database models used by the quiz application.
It includes models for quiz problems, user responses, and system configuration.
"""

from typing import Optional
from pydantic import BaseModel
from sqlmodel import SQLModel, Field

# Default configuration values
DEFAULT_ROBOT_REACH = 1750  # millimeters
DEFAULT_MAX_BOX_HEIGHT = 150  # millimeters  
DEFAULT_TIMEOUT_SECONDS = 10  # seconds

class Configuration(SQLModel, table=True):
    """
    System configuration settings for the quiz application.
    
    This model stores global settings that control quiz behavior,
    such as timeout values and robot specifications.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    max_box_height: int = Field(
        default=DEFAULT_MAX_BOX_HEIGHT, 
        description="Maximum height of a box in millimeters for quiz problems"
    )
    timeout_seconds: int = Field(
        default=DEFAULT_TIMEOUT_SECONDS, 
        description="Timeout in seconds for user to answer quiz questions"
    )
    robot_reach: int = Field(
        default=DEFAULT_ROBOT_REACH, 
        description="Robot arm reach distance in millimeters"
    )

class Quiz(SQLModel, table=True):
    """
    Individual quiz problem and user response.
    
    Each quiz record represents one problem presented to the user,
    including the problem parameters and the user's response.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    box_height: int = Field(description="Height of the box in millimeters")
    num_boxes: int = Field(description="Number of boxes in the problem")
    can_reach: Optional[bool] = Field(
        default=None, 
        description="User's answer: whether the robot can reach all boxes"
    )
    correct: Optional[bool] = Field(
        default=None, 
        description="Whether the user's answer was correct (auto-calculated)"
    )
    
class ApplicationStateResponse(BaseModel):
    state: str
    time_remaining: Optional[int] = None