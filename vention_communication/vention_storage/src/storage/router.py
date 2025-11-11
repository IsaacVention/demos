from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Body,
    Response,
    UploadFile,
    File,
    status,
)
from vention_storage.src.storage.accessor import ModelAccessor
from vention_storage.src.storage.services.crud_service import (
    CrudService,
    CrudError,
    NotFoundError,
    ConflictError,
    ValidationError,
    UnsupportedError,
)
from vention_storage.src.storage.services.database_service import (
    DatabaseService,
    DatabaseError,
)
from storage.utils import Operation


__all__ = ["build_router"]

DEFAULT_MAX_RECORDS_PER_MODEL = 100


# ---------------------------------------------------------
# Utilities
# ---------------------------------------------------------


def get_actor(request: Request) -> str:
    actor = request.headers.get("X-User")
    if not actor:
        raise HTTPException(status_code=400, detail="Missing X-User header")
    return actor


# ---------------------------------------------------------
# Router builder
# ---------------------------------------------------------


def build_router(
    *,
    accessors: Sequence[ModelAccessor[Any]],
    max_records_per_model: Optional[int] = DEFAULT_MAX_RECORDS_PER_MODEL,
    enable_db_routes: bool = True,
) -> APIRouter:
    """
    Build a unified FastAPI router exposing both CRUD and database utilities.

    Includes:
      - One CRUD router per accessor (e.g. /users, /jobs)
      - Optional /db endpoints (health, audit, export, backup, restore)
    """
    router = APIRouter()

    # -----------------------------------------------------
    # Per-model CRUD endpoints
    # -----------------------------------------------------
    for accessor in accessors:
        crud = CrudService(accessor, max_records=max_records_per_model)
        sub = APIRouter(prefix=f"/{accessor.component}", tags=[accessor.component])

        @sub.get("/", response_model=List[accessor.model])  # type: ignore
        def list_records(include_deleted: bool = Query(False)):
            try:
                return crud.list_records(include_deleted=include_deleted)
            except CrudError as e:
                raise _to_http(e)

        @sub.get("/{record_id}", response_model=accessor.model)  # type: ignore
        def get_record(record_id: int, include_deleted: bool = Query(False)):
            try:
                return crud.get_record(record_id, include_deleted=include_deleted)
            except CrudError as e:
                raise _to_http(e)

        @sub.post("/", response_model=accessor.model)  # type: ignore
        def create_record(
            payload: Dict[str, Any] = Body(...), actor: str = Depends(get_actor)
        ):
            try:
                return crud.create_record(payload, actor)
            except CrudError as e:
                raise _to_http(e)

        @sub.put("/{record_id}", response_model=accessor.model)
        def update_record(
            record_id: int,
            payload: Dict[str, Any] = Body(...),
            response: Optional[Response] = None,
            actor: str = Depends(get_actor),
        ) -> Any:
            try:
                obj: Any = crud.update_record(record_id, payload, actor)
                # If new record was created, emulate 201 Created
                if not crud.accessor.get(record_id, include_deleted=True):
                    if response is not None:
                        response.status_code = status.HTTP_201_CREATED
                return obj
            except CrudError as e:
                raise _to_http(e)

        @sub.delete("/{record_id}")
        def delete_record(
            record_id: int, actor: str = Depends(get_actor)
        ) -> Dict[str, str]:
            try:
                crud.delete_record(record_id, actor)
                return {"status": "deleted"}
            except CrudError as e:
                raise _to_http(e)

        @sub.post("/{record_id}/restore")
        def restore_record(
            record_id: int, actor: str = Depends(get_actor)
        ) -> Dict[str, Any]:
            try:
                return crud.restore_record(record_id, actor)
            except CrudError as e:
                raise _to_http(e)

        router.include_router(sub)

    # -----------------------------------------------------
    # /db endpoints
    # -----------------------------------------------------
    if enable_db_routes:
        db = DatabaseService()
        db_router = APIRouter(prefix="/db", tags=["db"])

        @db_router.get("/health")
        def health() -> Dict[str, str]:
            try:
                return db.health()
            except DatabaseError as e:
                raise _to_http(e)

        @db_router.get("/audit")
        def audit(
            component: Optional[str] = Query(None),
            record_id: Optional[int] = Query(None),
            actor: Optional[str] = Query(None),
            operation: Optional[str] = Query(None),
            since: Optional[str] = Query(None),
            until: Optional[str] = Query(None),
            limit: int = Query(db.audit_default_limit),
            offset: int = Query(0),
        ) -> List[Any]:
            try:
                # Convert string types to proper types
                operation_op: Optional[Operation] = None
                if operation is not None:
                    if operation not in (
                        "create",
                        "update",
                        "delete",
                        "soft_delete",
                        "restore",
                    ):
                        raise ValueError(f"Invalid operation: {operation}")
                    operation_op = operation  # type: ignore

                since_dt: Optional[datetime] = None
                if since is not None:
                    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))

                until_dt: Optional[datetime] = None
                if until is not None:
                    until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))

                return db.read_audit(
                    component=component,
                    record_id=record_id,
                    actor=actor,
                    operation=operation_op,
                    since=since_dt,
                    until=until_dt,
                    limit=limit,
                    offset=offset,
                )
            except DatabaseError as e:
                raise _to_http(e)

        @db_router.get("/diagram.svg", response_class=Response)
        def diagram_svg() -> Response:
            try:
                svg_bytes = db.schema_diagram_svg()
                return Response(content=svg_bytes, media_type="image/svg+xml")
            except DatabaseError as e:
                raise _to_http(e)

        @db_router.get("/export.zip")
        def export_zip() -> Response:
            try:
                data = db.export_zip()
                return Response(
                    content=data,
                    media_type="application/zip",
                    headers={
                        "Content-Disposition": 'attachment; filename="export.zip"'
                    },
                )
            except DatabaseError as e:
                raise _to_http(e)

        @db_router.get("/backup.sqlite")
        def backup_sqlite() -> Response:
            try:
                result = db.backup_sqlite()
                headers = {
                    "Content-Disposition": f'attachment; filename="{result["filename"]}"'
                }
                return Response(
                    content=result["data"],
                    media_type="application/x-sqlite3",
                    headers=headers,
                )
            except DatabaseError as e:
                raise _to_http(e)

        @db_router.post("/restore")
        async def restore_sqlite(
            file: UploadFile = File(...),
            integrity_check: bool = Query(True),
            dry_run: bool = Query(False),
        ) -> Dict[str, Any]:
            try:
                content = await file.read()
                filename = file.filename or "upload.sqlite"
                return db.restore_sqlite(
                    content,
                    filename=filename,
                    integrity_check=integrity_check,
                    dry_run=dry_run,
                )
            except DatabaseError as e:
                raise _to_http(e)

        router.include_router(db_router)

    return router


# ---------------------------------------------------------
# Error mapping
# ---------------------------------------------------------


def _to_http(exc: Exception) -> HTTPException:
    """Map service exceptions to HTTP errors."""
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, UnsupportedError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, DatabaseError):
        code_map = {
            "DEPENDENCY_ERROR": 503,
            "VALIDATION_ERROR": 422,
            "OPERATIONAL_ERROR": 503,
        }
        return HTTPException(status_code=code_map.get(exc.code, 500), detail=str(exc))
    if isinstance(exc, CrudError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))
