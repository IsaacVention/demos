from sqlmodel import SQLModel, Field

class Gripper(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    length: float
    width: float

    def get_center_of_mass(self) -> tuple[float, float]:
        return (self.length / 2, self.width / 2)