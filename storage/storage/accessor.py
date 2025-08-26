from __future__ import annotations

from storage.utils import utcnow
from typing import Generic, List, Optional, Sequence, Type, cast, Any

from sqlmodel import SQLModel, Session, select

from storage.auditor import audit_operation
from storage.database import transaction, get_engine
from storage.hooks import HookRegistry, HookFn
from typing import Callable
from storage.utils import ModelType


class ModelAccessor(Generic[ModelType]):
    """
    Accessor for a single SQLModel type with:
      - strongly-typed lifecycle hooks (before/after insert/update/delete)
      - atomic writes with auditing
      - optional soft delete (if model defines `deleted_at`)
      - batch helpers
      - session binding for use inside hooks (cascades, etc.)
    """

    def __init__(self, model: Type[ModelType], component_name: str) -> None:
        self.model = model
        self.component = component_name
        self._hooks: HookRegistry[ModelType] = HookRegistry()

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

    # ---------- Session binder (for use inside hooks) ----------
    def bind(self, session: Session) -> "BoundAccessor[ModelType]":
        return BoundAccessor(self.model, self.component, session)

    # ---------- Reads ----------
    def get(self, id: int, *, include_deleted: bool = False) -> Optional[ModelType]:
        """Fetch by PK. If model has `deleted_at`, exclude soft-deleted unless include_deleted=True."""
        with Session(get_engine()) as session:
            obj = session.get(self.model, id)
            if obj is None:
                return None
            if hasattr(obj, "deleted_at") and not include_deleted:
                if getattr(obj, "deleted_at") is not None:
                    return None
            return cast(ModelType, obj)

    def all(self, *, include_deleted: bool = False) -> List[ModelType]:
        """List all. If model has `deleted_at`, exclude soft-deleted unless include_deleted=True."""
        with Session(get_engine()) as session:
            stmt = select(self.model)
            if hasattr(self.model, "deleted_at") and not include_deleted:
                stmt = stmt.where(getattr(self.model, "deleted_at").is_(None))
            return cast(List[ModelType], session.exec(stmt).all())

    # ---------- Writes (atomic with audit) ----------
    def insert(self, obj: ModelType, *, actor: str = "internal") -> ModelType:
        with transaction() as session:
            self._hooks.emit("before_insert", session=session, instance=obj)

            session.add(obj)
            session.flush()
            session.refresh(obj)

            audit_operation(
                session=session,
                component=self.component,
                operation="create",
                record_id=int(getattr(obj, "id")),
                actor=actor,
                before=None,
                after=obj.model_dump(),
            )

            self._hooks.emit("after_insert", session=session, instance=obj)
            return obj

    def save(self, obj: ModelType, *, actor: str = "internal") -> ModelType:
        """Create or update based on presence of `id` (upsert-by-id semantics)."""
        obj_id = cast(Optional[int], getattr(obj, "id", None))
        if obj_id is None:
            return self.insert(obj, actor=actor)

        with transaction() as session:
            existing = session.get(self.model, obj_id)
            if existing is None:
                return self.insert(obj, actor=actor)

            before = existing.model_dump()

            merged = session.merge(obj)
            self._hooks.emit("before_update", session=session, instance=merged)

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

            self._hooks.emit("after_update", session=session, instance=merged)
            return cast(ModelType, merged)

    def upsert(self, obj: ModelType, *, actor: str = "internal") -> ModelType:
        return self.save(obj, actor=actor)

    def delete(self, id: int, *, actor: str = "internal") -> bool:
        with transaction() as session:
            obj = session.get(self.model, id)
            if obj is None:
                return False

            self._hooks.emit("before_delete", session=session, instance=obj)

            op, before_payload, after_payload = _soft_or_hard_delete(session, obj)

            audit_operation(
                session=session,
                component=self.component,
                operation=op,
                record_id=id,
                actor=actor,
                before=before_payload,
                after=after_payload,
            )

            self._hooks.emit("after_delete", session=session, instance=obj)
            return True

    def restore(self, id: int, *, actor: str = "internal") -> bool:
        """If model has `deleted_at`, set it back to None and audit a 'restore'."""
        with transaction() as session:
            obj = session.get(self.model, id)
            if obj is None or not hasattr(obj, "deleted_at"):
                return False
            if getattr(obj, "deleted_at") is None:
                return True  # already active

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

    # ---------- Batch helpers ----------
    def insert_many(self, objs: Sequence[ModelType], *, actor: str = "internal") -> List[ModelType]:
        out: List[ModelType] = []
        with transaction() as session:
            for obj in objs:
                self._hooks.emit("before_insert", session=session, instance=obj)
                session.add(obj)
            session.flush()
            for obj in objs:
                session.refresh(obj)
                audit_operation(
                    session=session,
                    component=self.component,
                    operation="create",
                    record_id=int(getattr(obj, "id")),
                    actor=actor,
                    before=None,
                    after=obj.model_dump(),
                )
                self._hooks.emit("after_insert", session=session, instance=obj)
                out.append(obj)
        return out

    def delete_many(self, ids: Sequence[int], *, actor: str = "internal") -> int:
        count = 0
        with transaction() as session:
            for id_ in ids:
                obj = session.get(self.model, id_)
                if obj is None:
                    continue

                self._hooks.emit("before_delete", session=session, instance=obj)

                op, before_payload, after_payload = _soft_or_hard_delete(session, obj)

                audit_operation(
                    session=session,
                    component=self.component,
                    operation=op,
                    record_id=id_,
                    actor=actor,
                    before=before_payload,
                    after=after_payload,
                )

                self._hooks.emit("after_delete", session=session, instance=obj)
                count += 1
        return count


class BoundAccessor(Generic[ModelType]):
    """
    Session-bound view of a ModelAccessor for use INSIDE hooks or external
    transaction blocks so you can reuse the same auditing/soft-delete logic
    without opening a new transaction.
    """

    def __init__(self, model: Type[ModelType], component: str, session: Session) -> None:
        self.model = model
        self.component = component
        self.session = session

    def delete_many(self, ids: Sequence[int], *, actor: str = "internal") -> int:
        count = 0
        for id_ in ids:
            obj = self.session.get(self.model, id_)
            if obj is None:
                continue

            op, before_payload, after_payload = _soft_or_hard_delete(self.session, obj)

            audit_operation(
                session=self.session,
                component=self.component,
                operation=op,
                record_id=id_,
                actor=actor,
                before=before_payload,
                after=after_payload,
            )
            count += 1
        return count

    def delete(self, id: int, *, actor: str = "internal") -> bool:
        return self.delete_many([id], actor=actor) == 1


def _soft_or_hard_delete(
    session: Session, instance: SQLModel
) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    """
    Perform soft delete if the model defines `deleted_at`, otherwise hard delete.
    Returns (operation, before_payload, after_payload).
    """
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
