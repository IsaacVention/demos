from __future__ import annotations
from typing import Any, Dict, List, Optional, Sequence, Type

from pydantic import BaseModel, create_model

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
from vention_storage.src.storage.utils import parse_audit_operation, parse_audit_datetime


__all__ = ["build_storage_bundle"]


# ---------------------------------------------------------
# Shared Pydantic models for RPC I/O
# (camelCase aliases applied automatically by registry)
# ---------------------------------------------------------


class CrudListRequest(BaseModel):
    include_deleted: bool = False


class CrudGetRequest(BaseModel):
    record_id: int
    include_deleted: bool = False


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
# Helpers: Dynamic, strongly-typed models per SQLModel
# ---------------------------------------------------------


def make_list_response_model(model_cls: Type[Any], name: str) -> Type[BaseModel]:
    """
    <Name>ListResponse { records: List[model_cls] }
    """
    return create_model(
        f"{name}ListResponse",
        records=(List[model_cls], ...),
        __base__=BaseModel,
    )


def make_single_response_model(
    model_cls: Type[Any],
    name: str,
    field_name: str = "record",
) -> Type[BaseModel]:
    """
    <Name>Response { <field_name>: model_cls }
    """
    return create_model(
        f"{name}Response",
        **{field_name: (model_cls, ...)},
        __base__=BaseModel,
    )


def make_status_response_model(name: str) -> Type[BaseModel]:
    """
    <Name>StatusResponse { status: str }
    """
    return create_model(
        f"{name}StatusResponse",
        status=(str, ...),
        __base__=BaseModel,
    )


def make_create_request_model(model_cls: Type[Any], name: str) -> Type[BaseModel]:
    """
    <Name>CreateRequest { record: model_cls, actor: str }
    """
    return create_model(
        f"{name}CreateRequest",
        record=(model_cls, ...),
        actor=(str, ...),
        __base__=BaseModel,
    )


def make_update_request_model(model_cls: Type[Any], name: str) -> Type[BaseModel]:
    """
    <Name>UpdateRequest { recordId: int, record: model_cls, actor: str }
    """
    return create_model(
        f"{name}UpdateRequest",
        record_id=(int, ...),
        record=(model_cls, ...),
        actor=(str, ...),
        __base__=BaseModel,
    )


def make_dict_list_response_model(name: str) -> Type[BaseModel]:
    """
    <Name>ListResponse { records: List[Dict[str, Any]] }
    Used for audit rows etc.
    """
    return create_model(
        f"{name}ListResponse",
        records=(List[Dict[str, Any]], ...),
        __base__=BaseModel,
    )


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
    # Per-model CRUD actions (typed per model)
    # -----------------------------------------------------
    for accessor in accessors:
        model_cls = accessor.model
        model_name = accessor.component.capitalize()

        crud = CrudService(accessor, max_records=max_records_per_model)

        # -------- Typed request/response models for this model --------
        ListResponse = make_list_response_model(model_cls, model_name)
        GetResponse = make_single_response_model(model_cls, f"{model_name}Get")
        CreateRequest = make_create_request_model(model_cls, model_name)
        CreateResponse = make_single_response_model(model_cls, f"{model_name}Create")
        UpdateRequest = make_update_request_model(model_cls, model_name)
        UpdateResponse = make_single_response_model(model_cls, f"{model_name}Update")
        DeleteResponse = make_status_response_model(model_name)
        RestoreResponse = make_single_response_model(model_cls, f"{model_name}Restore")

        # ---------------- List ----------------
        async def list_records(
            req: CrudListRequest,
            _crud: CrudService = crud,
            _Resp: Type[BaseModel] = ListResponse,
        ) -> BaseModel:
            try:
                records = list(_crud.list_records(include_deleted=req.include_deleted))
                return _Resp(records=records)
            except CrudError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name=f"{model_name}_ListRecords",
                func=list_records,
                input_type=CrudListRequest,
                output_type=ListResponse,
            )
        )

        # ---------------- Get ----------------
        async def get_record(
            req: CrudGetRequest,
            _crud: CrudService = crud,
            _Resp: Type[BaseModel] = GetResponse,
        ) -> BaseModel:
            try:
                rec = _crud.get_record(
                    req.record_id, include_deleted=req.include_deleted
                )
                return _Resp(record=rec)
            except CrudError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name=f"{model_name}_GetRecord",
                func=get_record,
                input_type=CrudGetRequest,
                output_type=GetResponse,
            )
        )

        # ---------------- Create ----------------
        async def create_record(
            req: CreateRequest,
            _crud: CrudService = crud,
            _Resp: Type[BaseModel] = CreateResponse,
        ) -> BaseModel:
            try:
                # record is a typed Pydantic model → dump to dict for CrudService
                payload = req.record.model_dump(exclude_unset=True, by_alias=False)
                rec = _crud.create_record(payload, req.actor)
                return _Resp(record=rec)
            except CrudError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name=f"{model_name}_CreateRecord",
                func=create_record,
                input_type=CreateRequest,
                output_type=CreateResponse,
            )
        )

        # ---------------- Update ----------------
        async def update_record(
            req: UpdateRequest,
            _crud: CrudService = crud,
            _Resp: Type[BaseModel] = UpdateResponse,
        ) -> BaseModel:
            try:
                payload = req.record.model_dump(exclude_unset=True, by_alias=False)
                rec = _crud.update_record(req.record_id, payload, req.actor)
                return _Resp(record=rec)
            except CrudError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name=f"{model_name}_UpdateRecord",
                func=update_record,
                input_type=UpdateRequest,
                output_type=UpdateResponse,
            )
        )

        # ---------------- Delete ----------------
        async def delete_record(
            req: CrudDeleteRequest,
            _crud: CrudService = crud,
            _Resp: Type[BaseModel] = DeleteResponse,
        ) -> BaseModel:
            try:
                _crud.delete_record(req.record_id, req.actor)
                return _Resp(status="deleted")
            except CrudError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name=f"{model_name}_DeleteRecord",
                func=delete_record,
                input_type=CrudDeleteRequest,
                output_type=DeleteResponse,
            )
        )

        # ---------------- Restore ----------------
        async def restore_record(
            req: CrudRestoreRequest,
            _crud: CrudService = crud,
            _Resp: Type[BaseModel] = RestoreResponse,
        ) -> BaseModel:
            try:
                rec = _crud.restore_record(req.record_id, req.actor)
                return _Resp(record=rec)
            except CrudError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name=f"{model_name}_RestoreRecord",
                func=restore_record,
                input_type=CrudRestoreRequest,
                output_type=RestoreResponse,
            )
        )

    # -----------------------------------------------------
    # Database utilities
    # -----------------------------------------------------
    if enable_db_actions:
        db = DatabaseService()

        # ---- Health ----
        class HealthResponse(BaseModel):
            status: str

        async def health() -> HealthResponse:
            try:
                res = db.health()
                return HealthResponse(status=res.get("status", "ok"))
            except DatabaseError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name="Database_Health",
                func=health,
                input_type=None,
                output_type=HealthResponse,
            )
        )

        # ---- Audit ----
        AuditListResponse = make_dict_list_response_model("Audit")

        async def audit(req: AuditQueryRequest) -> AuditListResponse:
            try:
                operation_op = parse_audit_operation(req.operation)
                since_dt = parse_audit_datetime(req.since)
                until_dt = parse_audit_datetime(req.until)

                results = list(
                    db.read_audit(
                        component=req.component,
                        record_id=req.record_id,
                        actor=req.actor,
                        operation=operation_op,
                        since=since_dt,
                        until=until_dt,
                        limit=req.limit,
                        offset=req.offset,
                    )
                )
                return AuditListResponse(records=results)
            except DatabaseError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name="Database_ReadAudit",
                func=audit,
                input_type=AuditQueryRequest,
                output_type=AuditListResponse,
            )
        )

        # ---- Export zip ----
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

        # ---- Backup sqlite ----
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

        # ---- Restore sqlite ----
        class RestoreRequest(BaseModel):
            bytes: bytes
            filename: Optional[str] = "upload.sqlite"
            integrity_check: bool = True
            dry_run: bool = False

        class RestoreResponse(BaseModel):
            ok: bool
            message: Optional[str] = None

        async def restore_sqlite(req: RestoreRequest) -> RestoreResponse:
            try:
                result = db.restore_sqlite(
                    file_bytes=req.bytes,
                    filename=req.filename or "upload.sqlite",
                    integrity_check=req.integrity_check,
                    dry_run=req.dry_run,
                )
                return RestoreResponse(**result)
            except DatabaseError as e:
                raise _to_rpc(e)

        bundle.actions.append(
            ActionEntry(
                name="Database_RestoreSqlite",
                func=restore_sqlite,
                input_type=RestoreRequest,
                output_type=RestoreResponse,
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
        return ConnectError(
            code=mapping.get(exc.code, "internal"), message=str(exc)
        )
    if isinstance(exc, CrudError):
        return ConnectError(code="internal", message=str(exc))
    return ConnectError(code="internal", message=str(exc))
