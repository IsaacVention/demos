# /orchestrator/storage.py

import os
import importlib.util
from datetime import datetime
from typing import List, Type, Any
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from sqlmodel import SQLModel, create_engine, Session, select, Field
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy import Column, func

# You can adjust this limit per model if desired
MAX_RECORDS_PER_MODEL = 5

# SQLite database file in the /storage directory
DATABASE_URL = "sqlite:///./storage.db"

engine = create_engine(DATABASE_URL, echo=True)


# -------- AUDIT MODEL --------

class AuditLog(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    timestamp: datetime
    component: str
    operation: str  # create / update / delete
    record_id: int
    user: str
    diff: dict = Field(sa_column=Column(JSON))


# -------- MODEL DISCOVERY --------

def discover_models() -> List[tuple[str, Type[SQLModel]]]:
    """
    Finds all models.py files in /components and returns list of (component_name, SQLModel subclass)
    """
    models = []
    base_dir = os.path.dirname(__file__)
    components_dir = os.path.join(base_dir, "../components")
    for component in os.listdir(components_dir):
        model_path = os.path.join(components_dir, component, "models.py")
        if not os.path.isfile(model_path):
            continue

        spec = importlib.util.spec_from_file_location(f"{component}.models", model_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and issubclass(obj, SQLModel) and obj is not SQLModel:
                models.append((component, obj))
    return models


# -------- USER DEPENDENCY --------

def get_user(request: Request) -> str:
    """
    Extracts user from X-User header
    """
    user = request.headers.get("X-User")
    if not user:
        raise HTTPException(status_code=400, detail="Missing X-User header")
    return user


# -------- CRUD ROUTER BUILDER --------

def build_crud_router(component: str, model: Type[SQLModel]) -> APIRouter:
    """
    Creates an APIRouter for a single model, with auditing and max entries enforced
    """
    router = APIRouter(prefix=f"/{component}")

    @router.get("/", response_model=List[model])
    def list_records():
        with Session(engine) as session:
            results = session.exec(select(model)).all()
            return results

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
            if isinstance(count, tuple):
                count = count[0]

            if count >= MAX_RECORDS_PER_MODEL:
                raise HTTPException(status_code=409, detail=f"Max {MAX_RECORDS_PER_MODEL} records allowed")

            session.add(data)
            session.commit()
            session.refresh(data)

            audit = AuditLog(
                timestamp=datetime.utcnow(),
                component=component,
                operation="create",
                record_id=data.id,
                user=user,
                diff=data.dict()
            )
            session.add(audit)
            session.commit()
            return data

    @router.put("/{record_id}", response_model=model)
    def update_record(record_id: int, update_data: model, user: str = Depends(get_user)):
        with Session(engine) as session:
            obj = session.get(model, record_id)
            if not obj:
                raise HTTPException(status_code=404, detail="Not found")

            before = obj.model_dump()
            for k, v in update_data.dict(exclude_unset=True).items():
                if k != "id":
                    setattr(obj, k, v)


            session.add(obj)
            session.commit()
            session.refresh(obj)

            audit = AuditLog(
                timestamp=datetime.utcnow(),
                component=component,
                operation="update",
                record_id=record_id,
                user=user,
                diff={"before": before, "after": obj.model_dump()}
            )
            session.add(audit)
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

            audit = AuditLog(
                timestamp=datetime.utcnow(),
                component=component,
                operation="delete",
                record_id=record_id,
                user=user,
                diff=before
            )
            session.add(audit)
            session.commit()
            return JSONResponse(content={"status": "deleted"})

    return router


# -------- BOOTSTRAP FUNCTION --------

def bootstrap(app):
    """
    Orchestrates discovery, migration, and CRUD router registration
    """
    models = discover_models()

    # Create all tables (models + audit)
    SQLModel.metadata.create_all(engine)

    # Register CRUD routers
    for component, model in models:
        router = build_crud_router(component, model)
        app.include_router(router)

    # Audit log endpoint
    audit_router = APIRouter()

    @audit_router.get("/audit")
    def get_audit(limit: int = 10):
        with Session(engine) as session:
            entries = session.exec(
                select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
            ).all()
            return entries

    app.include_router(audit_router)

