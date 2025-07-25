from typing import List, Type
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from sqlmodel import SQLModel, Session, select
from sqlalchemy import func

from orchestrator.accessor import ModelAccessor
from orchestrator.db import engine
from orchestrator.auditor import audit_operation, AuditLog

MAX_RECORDS_PER_MODEL = 5


# -------- USER DEPENDENCY --------


def get_user(request: Request) -> str:
    user = request.headers.get("X-User")
    if not user:
        raise HTTPException(status_code=400, detail="Missing X-User header")
    return user


# -------- CRUD ROUTER BUILDER --------


def build_crud_router(component: str, model: Type[SQLModel]) -> APIRouter:
    router = APIRouter(prefix=f"/{component}")

    @router.get("/", response_model=List[model])
    def list_records():
        with Session(engine) as session:
            return session.exec(select(model)).all()

    @router.get("/{record_id}", response_model=model)
    def get_record(record_id: int):
        with Session(engine) as session:
            obj = session.get(model, record_id)
            if not obj:
                raise HTTPException(status_code=404, detail="Not found")
            return obj

    @router.post("/", response_model=model)
    def create_record(data: model, user: str = Depends(get_user)):
        with Session(engine) as session:
            count = session.exec(select(func.count()).select_from(model)).one()
            count = count[0] if isinstance(count, tuple) else count

            if count >= MAX_RECORDS_PER_MODEL:
                raise HTTPException(
                    status_code=409,
                    detail=f"Max {MAX_RECORDS_PER_MODEL} records allowed",
                )

            session.add(data)
            session.commit()
            session.refresh(data)

            audit_operation(
                session=session,
                component=component,
                operation="create",
                record_id=data.id,
                user=user,
                diff=data.model_dump(),
            )

            session.commit()
            return data

    @router.put("/{record_id}", response_model=model)
    def update_record(
        record_id: int, update_data: model, user: str = Depends(get_user)
    ):
        with Session(engine) as session:
            obj = session.get(model, record_id)
            if not obj:
                raise HTTPException(status_code=404, detail="Not found")

            before = obj.model_dump()
            for k, v in update_data.model_dump(exclude_unset=True).items():
                if k != "id":
                    setattr(obj, k, v)

            session.add(obj)
            session.commit()
            session.refresh(obj)

            audit_operation(
                session=session,
                component=component,
                operation="update",
                record_id=record_id,
                user=user,
                diff={"before": before, "after": obj.model_dump()},
            )

            session.commit()
            return obj

    @router.delete("/{record_id}")
    def delete_record(record_id: int, user: str = Depends(get_user)):
        with Session(engine) as session:
            obj = session.get(model, record_id)
            if not obj:
                raise HTTPException(status_code=404, detail="Not found")

            before = obj.model_dump()
            session.delete(obj)
            session.commit()

            audit_operation(
                session=session,
                component=component,
                operation="delete",
                record_id=record_id,
                user=user,
                diff=before,
            )

            session.commit()
            return JSONResponse(content={"status": "deleted"})

    return router


# -------- BOOTSTRAP FUNCTION --------


def bootstrap(app, models: List[tuple[str, Type[SQLModel], ModelAccessor]]):
    SQLModel.metadata.create_all(engine)

    for component, model, accessor in models:
        router = build_crud_router(component, model)
        app.include_router(router)

    audit_router = APIRouter()

    @audit_router.get("/audit")
    def get_audit(limit: int = 10):
        with Session(engine) as session:
            return session.exec(
                select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
            ).all()

    app.include_router(audit_router)
