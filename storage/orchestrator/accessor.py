from typing import TypeVar, Generic, Type, List, Optional
from sqlmodel import SQLModel, Session, select
from orchestrator.db import engine

T = TypeVar("T", bound=SQLModel)


class ModelAccessor(Generic[T]):
    def __init__(self, model: Type[T]):
        self.model = model

    def get(self, id: int) -> Optional[T]:
        with Session(engine) as session:
            return session.get(self.model, id)

    def all(self) -> List[T]:
        with Session(engine) as session:
            return session.exec(select(self.model)).all()

    def insert(self, data: T) -> T:
        with Session(engine) as session:
            session.add(data)
            session.commit()
            session.refresh(data)
            return data
        
    def update(self, id: int, updates: dict) -> Optional[T]:
        with Session(engine) as session:
            obj = session.get(self.model, id)
            if not obj:
                return None
            for key, value in updates.items():
                if hasattr(obj, key):
                    setattr(obj, key, value)
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return obj
        
    def delete(self, id: int) -> bool:
        with Session(engine) as session:
            obj = session.get(self.model, id)
            if not obj:
                return False
            session.delete(obj)
            session.commit()
            return True