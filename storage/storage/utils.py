from datetime import datetime, timezone
from typing import TypeVar
from sqlmodel import SQLModel

ModelType = TypeVar("ModelType", bound=SQLModel)

def utcnow() -> datetime:
    return datetime.now(timezone.utc)
