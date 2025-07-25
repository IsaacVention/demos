from typing import TypeVar, Generic, Type, List, Optional
from sqlmodel import SQLModel, Session, select
from orchestrator.db import engine
from orchestrator.auditor import audit_operation

T = TypeVar("T", bound=SQLModel)


class ModelAccessor(Generic[T]):
    def __init__(self, model: Type[T], component_name: str):
        self.model = model
        self.component = component_name

    def get(self, id: int) -> Optional[T]:
        with Session(engine) as session:
            return session.get(self.model, id)

    def all(self) -> List[T]:
        with Session(engine) as session:
            return session.exec(select(self.model)).all()

    def insert(self, data: T, user: str = "internal") -> T:
        with Session(engine) as session:
            session.add(data)
            session.commit()
            session.refresh(data)
            audit_operation(
                session=session,
                component=self.component,
                operation="create",
                record_id=data.id,
                user=user,
                diff=data.model_dump(),
            )
            session.commit()
            return data

    def delete(self, id: int, user: str = "internal") -> bool:
        with Session(engine) as session:
            obj = session.get(self.model, id)
            if not obj:
                return False
            before = obj.model_dump()
            session.delete(obj)
            session.commit()
            audit_operation(
                session=session,
                component=self.component,
                operation="delete",
                record_id=id,
                user=user,
                diff=before,
            )
            session.commit()
            return True


    def save(self, obj: T, user: str = "internal") -> T:
        with Session(engine) as session:
            before = None
            if obj.id:
                existing = session.get(self.model, obj.id)
                if existing:
                    before = existing.model_dump()

            merged = session.merge(obj)
            session.commit()
            session.refresh(merged)

            if before:
                audit_operation(
                    session=session,
                    component=self.component,
                    operation="update",
                    record_id=merged.id,
                    user=user,
                    diff={"before": before, "after": merged.model_dump()},
                )
            else:
                audit_operation(
                    session=session,
                    component=self.component,
                    operation="create",
                    record_id=merged.id,
                    user=user,
                    diff=merged.model_dump(),
                )

            session.commit()
            return merged
