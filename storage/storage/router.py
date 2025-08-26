# storage/router.py
from __future__ import annotations
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from storage.accessor import ModelAccessor

MAX_RECORDS_PER_MODEL = 5

def get_actor(request: Request) -> str:
    actor = request.headers.get("X-User")
    if not actor:
        raise HTTPException(status_code=400, detail="Missing X-User header")
    return actor

def build_crud_router(accessor: ModelAccessor[Any]) -> APIRouter:
    model = accessor.model
    router = APIRouter(prefix=f"/{accessor.component}")

    @router.get("/", response_model=List[model])  # type: ignore[arg-type]
    def list_records():
        print("Listing records")
        return accessor.all()

    @router.get("/{record_id}", response_model=model)  # type: ignore[arg-type]
    def get_record(record_id: int):
        obj = accessor.get(record_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Not found")
        return obj

    @router.post("/", response_model=model)  # type: ignore[arg-type]
    def create_record(payload: Dict[str, Any] = Body(...), actor: str = Depends(get_actor)):
        if len(accessor.all(include_deleted=True)) >= MAX_RECORDS_PER_MODEL:
            raise HTTPException(status_code=409, detail=f"Max {MAX_RECORDS_PER_MODEL} records allowed")
        obj = model(**payload)
        return accessor.insert(obj, actor=actor)

    @router.put("/{record_id}", response_model=model)  # type: ignore[arg-type]
    def update_record(record_id: int, payload: Dict[str, Any] = Body(...), actor: str = Depends(get_actor)):
        obj = model(id=record_id, **payload)
        return accessor.save(obj, actor=actor)

    @router.delete("/{record_id}")
    def delete_record(record_id: int, actor: str = Depends(get_actor)):
        ok = accessor.delete(record_id, actor=actor)
        if not ok:
            raise HTTPException(status_code=404, detail="Not found")
        return {"status": "deleted"}

    return router
