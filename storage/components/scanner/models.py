from sqlmodel import SQLModel, Field

class Scanner(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    port: int
    auto_tune: bool