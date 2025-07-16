from sqlmodel import SQLModel, Field

class Gripper(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    length: float
    width: float