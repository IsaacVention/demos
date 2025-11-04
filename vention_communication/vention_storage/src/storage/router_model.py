from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Body,
    Response,
    status,
)
from sqlalchemy.exc import DataError, IntegrityError, StatementError
    
from vention_storage.src.storage.accessor import ModelAccessor
from vention_storage.src.storage.utils import ModelType

__all__ = ["build_crud_router"]

DEFAULT_MAX_RECORDS_PER_MODEL = 100


def get_actor(request: Request) -> str:
    """
    Extract the audit actor from the `X-User` header. Eg: 'Operator', 'Admin', etc.

    Notes:
        - Required for **mutating** endpoints (POST, PUT, DELETE, restore).
        - Optional for read-only endpoints.
        - The value is stored verbatim in `AuditLog.actor`.
        - If missing on a mutating endpoint, a 400 error is returned.

    Returns:
        The `X-User` header value.

    Raises:
        HTTPException(400): If the header is missing for a mutating endpoint.
    """
    actor = request.headers.get("X-User")
    if not actor:
        raise HTTPException(status_code=400, detail="Missing X-User header")
    return actor


def build_crud_router(
    accessor: ModelAccessor[ModelType],
    *,
    max_records: Optional[int] = DEFAULT_MAX_RECORDS_PER_MODEL,
) -> APIRouter:
    """
    Build a FastAPI router exposing CRUD + restore endpoints for a single SQLModel component.
    """
    model: Type[ModelType] = accessor.model
    router = APIRouter(prefix=f"/{accessor.component}", tags=[accessor.component])

    # ---------------- READS ----------------

    @router.get("/", response_model=List[model])  # type: ignore[valid-type]
    def list_records(
        include_deleted: bool = Query(False, description="Include soft-deleted rows"),
    ) -> List[ModelType]:
        """
        List all records for this model.

        By default, soft-deleted records are excluded from results.

        Args:
            include_deleted (bool): Set to true to include soft-deleted records. Defaults to false.

        Returns:
            List[model]: List of model instances matching the criteria.
        """
        return accessor.all(include_deleted=include_deleted)

    @router.get("/{record_id}", response_model=model)
    def get_record(
        record_id: int,
        include_deleted: bool = Query(False, description="Include soft-deleted row"),
    ) -> ModelType:
        """
        Retrieve a single record by its ID.

        Args:
            record_id (int): ID of the record to fetch.
            include_deleted (bool): Set to true to allow returning a soft-deleted record. Defaults to false.

        Returns:
            model: The model instance if found.

        Raises:
            HTTPException 404: If the record does not exist or is soft-deleted (when include_deleted=false).
        """
        obj = accessor.get(record_id, include_deleted=include_deleted)
        if not obj:
            raise HTTPException(status_code=404, detail="Not found")
        return obj

    # ---------------- WRITES ----------------

    @router.post("/", response_model=model)
    def create_record(
        payload: Dict[str, Any] = Body(...),
        actor: str = Depends(get_actor),
    ) -> ModelType:
        """
        Create a new record.

        Args:
            payload (Dict[str, Any]): JSON body with the record fields.
            actor (str): User identifier from the `X-User` header.

        Returns:
            model: The newly created model instance.

        Raises:
            HTTPException 409: If the maximum number of records has been reached.
            HTTPException 422: If the payload violates schema or database constraints.
        """
        if max_records is not None:
            total = len(accessor.all(include_deleted=True))
            if total >= max_records:
                raise HTTPException(
                    status_code=409,
                    detail=f"Max {max_records} records allowed for {accessor.component}",
                )
        obj = model(**payload)

        try:
            return accessor.insert(obj, actor=actor)
        except (IntegrityError, DataError, StatementError) as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    @router.put("/{record_id}", response_model=model)
    def update_record(
        record_id: int,
        response: Response,
        payload: Dict[str, Any] = Body(...),
        actor: str = Depends(get_actor),
    ) -> ModelType:
        """
        Upsert a record (PUT semantics).

        Args:
            record_id (int): ID of the record to update or create.
            payload (Dict[str, Any]): JSON body with the record fields (the `id` key, if present, is ignored).
            actor (str): User identifier from the `X-User` header.
            response (Response): Used to adjust the HTTP status code.

        Returns:
            model: The updated or newly created model instance.

        If the record exists, it is updated in place (200 OK).
        If the record does not exist, it is created at this ID (201 Created).
        """
        existed = accessor.get(record_id, include_deleted=True) is not None

        # If this PUT will create a new row, enforce the max records.
        if not existed and max_records is not None:
            total = len(accessor.all(include_deleted=True))
            if total >= max_records:
                raise HTTPException(
                    status_code=409,
                    detail=f"Max {max_records} records allowed for {accessor.component}",
                )

        # Build instance (ignore `id` from body if present)
        payload_no_id = {key: value for key, value in payload.items() if key != "id"}
        obj = model(id=record_id, **payload_no_id)

        try:
            saved = accessor.save(obj, actor=actor)
        except (IntegrityError, DataError, StatementError) as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

        if not existed:
            response.status_code = status.HTTP_201_CREATED
        return saved

    @router.delete("/{record_id}")
    def delete_record(
        record_id: int,
        actor: str = Depends(get_actor),
    ) -> Dict[str, str]:
        """
        Delete a record by ID.

        If the model supports soft-delete, the record is marked as deleted.
        Otherwise, the record is permanently removed.

        Args:
            record_id (int): ID of the record to delete.
            actor (str): User identifier from the `X-User` header.

        Returns:
            dict: {"status": "deleted"} on success.

        Raises:
            HTTPException 404: If the record does not exist.
        """
        ok = accessor.delete(record_id, actor=actor)
        if not ok:
            raise HTTPException(status_code=404, detail="Not found")
        return {"status": "deleted"}

    # ---------------- RESTORE (soft-delete only) ----------------

    @router.post("/{record_id}/restore")
    def restore_record(
        record_id: int,
        actor: str = Depends(get_actor),
    ) -> Dict[str, Any]:
        """
        Restore a soft-deleted record.

        This endpoint only applies if the model has a `deleted_at` field.

        Args:
            record_id (int): ID of the record to restore.
            actor (str): User identifier from the `X-User` header.

        Returns:
            dict: {"status": "ok", "restored": True} if the record was restored,
                  {"status": "ok", "restored": False} if it was not soft-deleted.

        Raises:
            HTTPException 404: If the record does not exist.
            HTTPException 409: If the model does not support soft-delete/restore.
        """
        if not hasattr(accessor.model, "deleted_at"):
            raise HTTPException(
                status_code=409,
                detail=f"{accessor.component} does not support soft delete/restore",
            )

        obj = accessor.get(record_id, include_deleted=True)
        if not obj:
            raise HTTPException(status_code=404, detail="Not found")

        if getattr(obj, "deleted_at") is None:
            return {"status": "ok", "restored": False}

        accessor.restore(record_id, actor=actor)
        return {"status": "ok", "restored": True}

    return router
