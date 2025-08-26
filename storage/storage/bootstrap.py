# storage/bootstrap.py
from fastapi import FastAPI
from sqlmodel import SQLModel
from storage.database import get_engine, set_database_url
from storage.router import build_crud_router
from storage.auditor import AuditLog
from fastapi import APIRouter
from sqlmodel import Session, select
from typing import Any, Iterable, Dict, List, Optional
from storage.accessor import ModelAccessor

def bootstrap(
    app: FastAPI,
    *,
    accessors: Iterable[ModelAccessor[Any]],
    database_url: Optional[str] = None,
) -> None:
    if database_url is not None:
        set_database_url(database_url)

    engine = get_engine()
    SQLModel.metadata.create_all(engine)

    for acc in accessors:
        app.include_router(build_crud_router(acc))

    audit = APIRouter()

    @audit.get("/audit")
    def get_audit(limit: int = 10) -> List[Dict[str, Any]]:
        with Session(get_engine()) as s:
            rows: List[AuditLog] = s.exec(
                select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
            ).all()

        def to_ui(r: AuditLog) -> Dict[str, Any]:
            if r.before is None and r.after is not None:
                diff: Any = r.after
            elif r.before is not None or r.after is not None:
                diff = {"before": r.before, "after": r.after}
            else:
                diff = None
            return {
                "timestamp": r.timestamp.isoformat(),
                "user": r.actor,
                "operation": r.operation,
                "component": r.component,
                "diff": diff,
            }

        return [to_ui(r) for r in rows]

    app.include_router(audit)
