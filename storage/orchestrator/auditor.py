from datetime import datetime
from sqlmodel import SQLModel, Session
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy import Column
from sqlmodel import Field


class AuditLog(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    timestamp: datetime
    component: str
    operation: str  # create / update / delete
    record_id: int
    user: str
    diff: dict = Field(sa_column=Column(JSON))


def audit_operation(
    *,
    session: Session,
    component: str,
    operation: str,
    record_id: int,
    user: str = "system",
    diff: dict
):
    audit = AuditLog(
        timestamp=datetime.utcnow(),
        component=component,
        operation=operation,
        record_id=record_id,
        user=user,
        diff=diff,
    )
    session.add(audit)
