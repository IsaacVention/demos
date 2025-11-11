from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Type

from pydantic import BaseModel, create_model
from fastapi.encoders import jsonable_encoder

from src.vention_communication.entries import RpcBundle, ActionEntry
from src.vention_communication.errors import ConnectError

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
from vention_storage.src.storage.utils import Operation


__all__ = ["build_storage_bundle"]


# ---------------------------------------------------------
# Shared Pydantic models for RPC I/O
# ---------------------------------------------------------


class CrudListRequest(BaseModel):
    include_deleted: bool = False


class CrudGetRequest(BaseModel):
    record_id: int
    include_deleted: bool = False


class CrudCreateRequest(BaseModel):
    payload: Dict[str, Any]
    actor: str


class CrudUpdateRequest(BaseModel):
    record_id: int
    payload: Dict[str, Any]
    actor: str


class CrudDeleteRequest(BaseModel):
    record_id: int
    actor: str


class CrudRestoreRequest(BaseModel):
    record_id: int
    actor: str


class AuditQueryRequest(BaseModel):
    component: Optional[str] = None
    record_id: Optional[int] = None
    actor: Optional[str] = None
    operation: Optional[str] = None
    since: Optional[str] = None
    until: Optional[str] = None
    limit: Optional[int] = None
    offset: int = 0


class FileResponse(BaseModel):
    filename: str
    bytes: bytes


# ---------------------------------------------------------
# Bundle builder
# ---------------------------------------------------------


def build_storage_bundle(
    *,
    accessors: Sequence[ModelAccessor[Any]],
    max_records_per_model: Optional[int] = 5,
    enable_db_actions: bool = True,
) -> RpcBundle:
    """
    Build a ConnectRPC RpcBundle exposing CRUD and database utilities.

    Includes:
      - CRUD actions for each ModelAccessor
      - Optional DB actions (health, audit, export, backup, restore)
    """
    bundle = RpcBundle()

    # -----------------------------------------------------
    # Per-model CRUD actions
    # -----------------------------------------------------
    for accessor in accessors:
        crud = CrudService(accessor, max_records=max_records_per_model)
        model_name = accessor.component.capitalize()
        model_cls: Type[BaseModel] = accessor.model

        # Dynamically create a typed list wrapper for the model
        ListResponse = create_model(
            f"{model_name}ListResponse",
            records=(List[model_cls], ...),
        )

        # ---------- LIST ----------
        async def list_records(
            req: CrudListRequest, _crud: CrudService = crud
        ) -> ListResponse:
            try:
                records = _crud.list_records(include_deleted=req.include_deleted)
                return ListResponse(records=jsonable_encoder(records))
            except CrudError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name=f"{model_name}_ListRecords",
                func=list_records,
                input_type=CrudListRequest,
                output_type=ListResponse,  # ✅ typed
            )
        )

        # ---------- GET ----------
        async def get_record(req: CrudGetRequest, _crud: CrudService = crud) -> model_cls:
            try:
                record = _crud.get_record(
                    req.record_id, include_deleted=req.include_deleted
                )
                return jsonable_encoder(record)
            except CrudError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name=f"{model_name}_GetRecord",
                func=get_record,
                input_type=CrudGetRequest,
                output_type=model_cls,  # ✅ typed
            )
        )

        # ---------- CREATE ----------
        async def create_record(
            req: CrudCreateRequest, _crud: CrudService = crud
        ) -> model_cls:
            try:
                record = _crud.create_record(req.payload, req.actor)
                return jsonable_encoder(record)
            except CrudError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name=f"{model_name}_CreateRecord",
                func=create_record,
                input_type=CrudCreateRequest,
                output_type=model_cls,
            )
        )

        # ---------- UPDATE ----------
        async def update_record(
            req: CrudUpdateRequest, _crud: CrudService = crud
        ) -> model_cls:
            try:
                record = _crud.update_record(req.record_id, req.payload, req.actor)
                return jsonable_encoder(record)
            except CrudError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name=f"{model_name}_UpdateRecord",
                func=update_record,
                input_type=CrudUpdateRequest,
                output_type=model_cls,
            )
        )

        # ---------- DELETE ----------
        async def delete_record(
            req: CrudDeleteRequest, _crud: CrudService = crud
        ) -> Dict[str, str]:
            try:
                _crud.delete_record(req.record_id, req.actor)
                return {"status": "deleted"}
            except CrudError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name=f"{model_name}_DeleteRecord",
                func=delete_record,
                input_type=CrudDeleteRequest,
                output_type=Dict[str, str],
            )
        )

        # ---------- RESTORE ----------
        async def restore_record(
            req: CrudRestoreRequest, _crud: CrudService = crud
        ) -> model_cls:
            try:
                record = _crud.restore_record(req.record_id, req.actor)
                return jsonable_encoder(record)
            except CrudError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name=f"{model_name}_RestoreRecord",
                func=restore_record,
                input_type=CrudRestoreRequest,
                output_type=model_cls,
            )
        )

    # -----------------------------------------------------
    # Database utilities
    # -----------------------------------------------------
    if enable_db_actions:
        db = DatabaseService()

        async def health() -> Dict[str, str]:
            try:
                return jsonable_encoder(db.health())
            except DatabaseError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name="Database_Health",
                func=health,
                input_type=None,
                output_type=Dict[str, str],
            )
        )

        async def audit(req: AuditQueryRequest) -> Dict[str, Any]:
            try:
                operation: Optional[Operation] = None
                if req.operation is not None:
                    if req.operation not in (
                        "create",
                        "update",
                        "delete",
                        "soft_delete",
                        "restore",
                    ):
                        raise ValueError(f"Invalid operation: {req.operation}")
                    operation = req.operation  # type: ignore

                since_dt = (
                    datetime.fromisoformat(req.since.replace("Z", "+00:00"))
                    if req.since
                    else None
                )
                until_dt = (
                    datetime.fromisoformat(req.until.replace("Z", "+00:00"))
                    if req.until
                    else None
                )

                results = db.read_audit(
                    component=req.component,
                    record_id=req.record_id,
                    actor=req.actor,
                    operation=operation,
                    since=since_dt,
                    until=until_dt,
                    limit=req.limit,
                    offset=req.offset,
                )
                return {"records": jsonable_encoder(results)}
            except DatabaseError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name="Database_ReadAudit",
                func=audit,
                input_type=AuditQueryRequest,
                output_type=Dict[str, Any],
            )
        )

        async def export_zip() -> FileResponse:
            try:
                data = db.export_zip()
                return FileResponse(filename="export.zip", bytes=data)
            except DatabaseError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name="Database_ExportZip",
                func=export_zip,
                input_type=None,
                output_type=FileResponse,
            )
        )

        async def backup_sqlite() -> FileResponse:
            try:
                result = db.backup_sqlite()
                return FileResponse(filename=result["filename"], bytes=result["data"])
            except DatabaseError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name="Database_BackupSqlite",
                func=backup_sqlite,
                input_type=None,
                output_type=FileResponse,
            )
        )

        class RestoreRequest(BaseModel):
            bytes: bytes
            filename: Optional[str] = "upload.sqlite"
            integrity_check: bool = True
            dry_run: bool = False

        async def restore_sqlite(req: RestoreRequest) -> Dict[str, Any]:
            try:
                return jsonable_encoder(
                    db.restore_sqlite(
                        file_bytes=req.bytes,
                        filename=req.filename or "upload.sqlite",
                        integrity_check=req.integrity_check,
                        dry_run=req.dry_run,
                    )
                )
            except DatabaseError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name="Database_RestoreSqlite",
                func=restore_sqlite,
                input_type=RestoreRequest,
                output_type=Dict[str, Any],
            )
        )

    return bundle


# ---------------------------------------------------------
# Error mapping
# ---------------------------------------------------------


def _to_rpc(exc: Exception) -> ConnectError:
    """Map service exceptions to ConnectRPC RpcError codes."""
    if isinstance(exc, NotFoundError):
        return ConnectError(code="not_found", message=str(exc))
    if isinstance(exc, ConflictError):
        return ConnectError(code="failed_precondition", message=str(exc))
    if isinstance(exc, ValidationError):
        return ConnectError(code="invalid_argument", message=str(exc))
    if isinstance(exc, UnsupportedError):
        return ConnectError(code="failed_precondition", message=str(exc))
    if isinstance(exc, DatabaseError):
        mapping = {
            "DEPENDENCY_ERROR": "unavailable",
            "VALIDATION_ERROR": "invalid_argument",
            "OPERATIONAL_ERROR": "internal",
        }
        return ConnectError(code=mapping.get(exc.code, "internal"), message=str(exc))
    if isinstance(exc, CrudError):
        return ConnectError(code="internal", message=str(exc))
    return ConnectError(code="internal", message=str(exc))
