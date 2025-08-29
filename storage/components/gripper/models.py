from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class Gripper(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    length: float
    width: float
    deleted_at: Optional[datetime] = Field(default=None, index=True)

    def get_center_of_mass(self) -> tuple[float, float]:
        return (self.length / 2, self.width / 2)