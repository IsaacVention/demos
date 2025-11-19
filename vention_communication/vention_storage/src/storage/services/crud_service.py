# vention_storage/src/storage/services/crud_service.py

from __future__ import annotations
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import DataError, IntegrityError, StatementError
from vention_storage.src.storage.accessor import ModelAccessor
from vention_storage.src.storage.utils import ModelType


__all__ = ["CrudService", "CrudError"]


# ---------------------------------------------------------
# Exceptions (transport-agnostic)
# ---------------------------------------------------------


class CrudError(Exception):
    """Base class for CRUD-related errors."""

    def __init__(self, message: str, code: str = "UNKNOWN"):
        super().__init__(message)
        self.code = code


class NotFoundError(CrudError):
    def __init__(self, message: str = "Not found"):
        super().__init__(message, code="NOT_FOUND")


class ConflictError(CrudError):
    def __init__(self, message: str):
        super().__init__(message, code="CONFLICT")


class ValidationError(CrudError):
    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR")


class UnsupportedError(CrudError):
    def __init__(self, message: str):
        super().__init__(message, code="UNSUPPORTED_OPERATION")


# ---------------------------------------------------------
# CRUD Service
# ---------------------------------------------------------


class CrudService:
    """
    Transport-agnostic CRUD logic for SQLModel components.

    Provides safe, actor-aware CRUD operations. Intended to be reused
    by both FastAPI routers (REST) and RPC bundles (ConnectRPC).
    """

    def __init__(
        self,
        accessor: ModelAccessor[ModelType],
        *,
        max_records: Optional[int] = None,
    ) -> None:
        self.accessor = accessor
        self.max_records = max_records

    # ---------------- READS ----------------

    def list_records(self, *, include_deleted: bool = False) -> List[ModelType]:
        """Return all records for this model."""
        return self.accessor.all(include_deleted=include_deleted)

    def get_record(
        self,
        record_id: int,
        *,
        include_deleted: bool = False,
    ) -> ModelType:  # type: ignore[type-var]
        """Retrieve a single record by ID."""
        obj = self.accessor.get(record_id, include_deleted=include_deleted)
        if not obj:
            raise NotFoundError()
        return obj

    # ---------------- WRITES ----------------

    def create_record(self, payload: Dict[str, Any], actor: str) -> ModelType:  # type: ignore[type-var]
        """Insert a new record into the database."""
        if self.max_records is not None:
            total = len(self.accessor.all(include_deleted=True))
            if total >= self.max_records:
                raise ConflictError(
                    f"Max {self.max_records} records allowed for {self.accessor.component}"
                )

        obj = self.accessor.model(**payload)
        try:
            result = self.accessor.insert(obj, actor=actor)
            return result
        except (IntegrityError, DataError, StatementError) as e:
            raise ValidationError(str(e)) from e

    def update_record(
        self,
        record_id: int,
        payload: Dict[str, Any],
        actor: str,
    ) -> ModelType:  # type: ignore[type-var]
        """Upsert a record (PUT semantics)."""
        existed = self.accessor.get(record_id, include_deleted=True) is not None

        if not existed and self.max_records is not None:
            total = len(self.accessor.all(include_deleted=True))
            if total >= self.max_records:
                raise ConflictError(
                    f"Max {self.max_records} records allowed for {self.accessor.component}"
                )

        payload_no_id = {k: v for k, v in payload.items() if k != "id"}
        obj = self.accessor.model(id=record_id, **payload_no_id)

        try:
            saved = self.accessor.save(obj, actor=actor)
        except (IntegrityError, DataError, StatementError) as e:
            raise ValidationError(str(e)) from e

        return saved

    def delete_record(self, record_id: int, actor: str) -> None:
        """Delete a record by ID (soft or hard)."""
        ok = self.accessor.delete(record_id, actor=actor)
        if not ok:
            raise NotFoundError()

    def restore_record(self, record_id: int, actor: str) -> ModelType:  # type: ignore[type-var]
        """Restore a soft-deleted record (if supported).
        
        Returns the restored model instance. If the record was already
        not deleted, returns it unchanged.
        """
        model_cls = self.accessor.model
        if not hasattr(model_cls, "deleted_at"):
            raise UnsupportedError(
                f"{self.accessor.component} does not support soft delete/restore"
            )

        obj = self.accessor.get(record_id, include_deleted=True)
        if not obj:
            raise NotFoundError()

        if getattr(obj, "deleted_at") is None:
            # already restored, return as-is
            return obj

        self.accessor.restore(record_id, actor=actor)
        # Fetch the restored record to return it
        restored = self.accessor.get(record_id, include_deleted=False)
        if not restored:
            raise NotFoundError("Record not found after restore")
        return restored
