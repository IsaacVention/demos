from __future__ import annotations

from contextlib import contextmanager
from typing import (
    Any,
    Callable,
    Generic,
    List,
    Optional,
    Sequence,
    Type,
    TypeVar,
    cast,
    Iterator,
)

from sqlmodel import SQLModel, Session, select

from vention_storage.src.storage.auditor import audit_operation
from vention_storage.src.storage import database
from vention_storage.src.storage.hooks import HookFn, HookRegistry, HookEvent
from vention_storage.src.storage.utils import ModelType, utcnow, Operation


WriteResult = TypeVar("WriteResult")


class ModelAccessor(Generic[ModelType]):
    """
    Accessor for a single SQLModel type with:
      - strongly-typed lifecycle hooks (before/after insert/update/delete)
      - atomic writes with auditing
      - optional soft delete (if model defines `deleted_at`)
      - batch helpers
      - implicit session reuse inside hooks (no .bind() needed)
    """

    def __init__(self, model: Type[ModelType], component_name: str) -> None:
        self.model = model
        self.component = component_name
        self._hooks: HookRegistry[ModelType] = HookRegistry()
        self._has_soft_delete = hasattr(model, "deleted_at")

    # ---------- Hook decorators ----------
    def before_insert(self) -> Callable[[HookFn[ModelType]], HookFn[ModelType]]:
        return self._hooks.decorator("before_insert")

    def after_insert(self) -> Callable[[HookFn[ModelType]], HookFn[ModelType]]:
        return self._hooks.decorator("after_insert")

    def before_update(self) -> Callable[[HookFn[ModelType]], HookFn[ModelType]]:
        return self._hooks.decorator("before_update")

    def after_update(self) -> Callable[[HookFn[ModelType]], HookFn[ModelType]]:
        return self._hooks.decorator("after_update")

    def before_delete(self) -> Callable[[HookFn[ModelType]], HookFn[ModelType]]:
        return self._hooks.decorator("before_delete")

    def after_delete(self) -> Callable[[HookFn[ModelType]], HookFn[ModelType]]:
        return self._hooks.decorator("after_delete")

    # ---------- Internal helpers ----------
    def _emit(self, event: HookEvent, *, session: Session, instance: ModelType) -> None:
        """Make this session visible to any accessor calls done inside hooks."""
        with database.use_session(session):
            self._hooks.emit(event, session=session, instance=instance)

    def _audit_create_operation(
        self, *, session: Session, instance: ModelType, actor: str
    ) -> None:
        """Audit a create operation."""
        audit_operation(
            session=session,
            component=self.component,
            operation="create",
            record_id=int(getattr(instance, "id")),
            actor=actor,
            before=None,
            after=instance.model_dump(),
        )

    def _run_write(self, fn: Callable[[Session], WriteResult]) -> WriteResult:
        """Run a write op using the current session if present, else open a transaction."""
        existing = database.CURRENT_SESSION.get()
        if existing is not None:
            return fn(existing)
        with database.transaction() as session:
            return fn(session)

    @contextmanager
    def _read_session(self) -> Iterator[Session]:
        """Reuse current session if present; otherwise open a short-lived one."""
        existing = database.CURRENT_SESSION.get()
        if existing is not None:
            yield existing
        else:
            with Session(database.get_engine(), expire_on_commit=False) as session:
                yield session

    # ---------- Reads ----------
    def get(self, id: int, *, include_deleted: bool = False) -> Optional[ModelType]:
        """Get a single model by id."""
        with self._read_session() as session:
            obj = session.get(self.model, id)
            if obj is None:
                return None
            if self._has_soft_delete and not include_deleted:
                if getattr(obj, "deleted_at") is not None:
                    return None
            return cast(ModelType, obj)

    def all(self, *, include_deleted: bool = False) -> List[ModelType]:
        """Get all models."""
        with self._read_session() as session:
            statement = select(self.model)
            if self._has_soft_delete and not include_deleted:
                statement = statement.where(getattr(self.model, "deleted_at").is_(None))
            return cast(List[ModelType], session.exec(statement).all())

    # ---------- Writes ----------
    def insert(self, obj: ModelType, *, actor: str = "internal") -> ModelType:
        """Insert a new model."""

        def write_operation(session: Session) -> ModelType:
            self._emit("before_insert", session=session, instance=obj)
            session.add(obj)
            session.flush()
            session.refresh(obj)
            self._audit_create_operation(session=session, instance=obj, actor=actor)
            self._emit("after_insert", session=session, instance=obj)
            return obj

        return self._run_write(write_operation)

    def save(self, obj: ModelType, *, actor: str = "internal") -> ModelType:
        """Save a model, creating it if it doesn't exist."""

        def write_operation(session: Session) -> ModelType:
            obj_id = cast(Optional[int], getattr(obj, "id", None))
            if obj_id is None:
                return self.insert(obj, actor=actor)

            current = session.get(self.model, obj_id)
            if current is None:
                return self.insert(obj, actor=actor)

            before = current.model_dump()
            merged = session.merge(obj)
            self._emit("before_update", session=session, instance=merged)
            session.flush()
            session.refresh(merged)
            audit_operation(
                session=session,
                component=self.component,
                operation="update",
                record_id=int(getattr(merged, "id")),
                actor=actor,
                before=before,
                after=merged.model_dump(),
            )
            self._emit("after_update", session=session, instance=merged)
            return cast(ModelType, merged)

        return self._run_write(write_operation)

    def delete(self, id: int, *, actor: str = "internal") -> bool:
        """Delete a model."""

        def write_operation(session: Session) -> bool:
            obj = session.get(self.model, id)
            if obj is None:
                return False
            self._emit("before_delete", session=session, instance=obj)
            op_name, before_payload, after_payload = _soft_or_hard_delete(session, obj)
            audit_operation(
                session=session,
                component=self.component,
                operation=op_name,
                record_id=id,
                actor=actor,
                before=before_payload,
                after=after_payload,
            )
            self._emit("after_delete", session=session, instance=obj)
            return True

        return self._run_write(write_operation)

    def restore(self, id: int, *, actor: str = "internal") -> bool:
        """Restore a soft-deleted model."""

        def write_operation(session: Session) -> bool:
            obj = session.get(self.model, id)
            if obj is None or not self._has_soft_delete:
                return False
            if getattr(obj, "deleted_at") is None:
                return True
            before = obj.model_dump()
            setattr(obj, "deleted_at", None)
            session.add(obj)
            session.flush()
            session.refresh(obj)
            audit_operation(
                session=session,
                component=self.component,
                operation="restore",
                record_id=id,
                actor=actor,
                before=before,
                after=obj.model_dump(),
            )
            return True

        return self._run_write(write_operation)

    # ---------- Batch helpers ----------
    def insert_many(
        self, objs: Sequence[ModelType], *, actor: str = "internal"
    ) -> List[ModelType]:
        """Insert multiple models."""

        def write_operation(session: Session) -> List[ModelType]:
            out: List[ModelType] = []
            for obj in objs:
                self._emit("before_insert", session=session, instance=obj)
                session.add(obj)
            session.flush()
            for obj in objs:
                session.refresh(obj)
                self._audit_create_operation(session=session, instance=obj, actor=actor)
                self._emit("after_insert", session=session, instance=obj)
                out.append(obj)
            return out

        return self._run_write(write_operation)

    def delete_many(self, ids: Sequence[int], *, actor: str = "internal") -> int:
        """Delete multiple models."""

        def write_operation(session: Session) -> int:
            count = 0
            for id_ in ids:
                obj = session.get(self.model, id_)
                if obj is None:
                    continue
                self._emit("before_delete", session=session, instance=obj)
                op_name, before_payload, after_payload = _soft_or_hard_delete(
                    session, obj
                )
                audit_operation(
                    session=session,
                    component=self.component,
                    operation=op_name,
                    record_id=id_,
                    actor=actor,
                    before=before_payload,
                    after=after_payload,
                )
                self._emit("after_delete", session=session, instance=obj)
                count += 1
            return count

        return self._run_write(write_operation)


def _soft_or_hard_delete(
    session: Session, instance: SQLModel
) -> tuple[Operation, dict[str, Any], dict[str, Any] | None]:
    """Soft delete if model defines `deleted_at`, else hard delete."""
    before_payload = instance.model_dump()
    if hasattr(instance, "deleted_at"):
        setattr(instance, "deleted_at", utcnow())
        session.add(instance)
        session.flush()
        after_payload = instance.model_dump()
        return "soft_delete", before_payload, after_payload
    else:
        session.delete(instance)
        return "delete", before_payload, None
