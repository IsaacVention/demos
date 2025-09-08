from __future__ import annotations

from typing import List, cast
from sqlmodel import Session, SQLModel, select

from storage import database as db
from storage.accessor import ModelAccessor
from storage.auditor import AuditLog
from storage_tests.fixtures import StorageTestCase, SoftDeleteModel, HardDeleteModel


class TestModelAccessor(StorageTestCase):
    def setUp(self) -> None:
        super().setUp()
        # Accessors under test
        self.soft = ModelAccessor(SoftDeleteModel, "softs")
        self.hard = ModelAccessor(HardDeleteModel, "hards")

    # ----- helpers
    def _count(self, model: type[SQLModel]) -> int:
        with Session(self.engine) as session:
            return len(session.exec(select(model)).all())

    def _audits(self) -> List[AuditLog]:
        with Session(self.engine) as session:
            return cast(
                List[AuditLog],
                session.exec(select(AuditLog).order_by(AuditLog.id)).all(),
            )

    # ----- core CRUD + reads
    def test_insert_and_reads(self) -> None:
        """Tests insert, get, all, and audit creation"""
        thing = self.soft.insert(SoftDeleteModel(name="thing"))
        self.assertIsNotNone(thing.id)
        self.assertEqual(self._count(SoftDeleteModel), 1)

        # get / all
        assert thing.id is not None
        got = self.soft.get(int(thing.id))
        self.assertIsNotNone(got)
        all_rows = self.soft.all()
        self.assertEqual(len(all_rows), 1)

        # get() missing => None (covers branch)
        self.assertIsNone(self.hard.get(999_999))

        # audit created
        audits = self._audits()
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].operation, "create")
        self.assertEqual(audits[0].component, "softs")

    def test_update_and_upsert_alias_and_session_reuse_in_hook(self) -> None:
        """Tests update, upsert alias, and session reuse in hook"""

        @self.soft.before_insert()
        def _spawn_hard(session: Session, instance: SoftDeleteModel) -> None:
            self.hard.insert(
                HardDeleteModel(name=f"child-{instance.name}"), actor="hook"
            )

        thing = self.soft.insert(SoftDeleteModel(name="parent"))
        self.assertEqual(self._count(SoftDeleteModel), 1)
        self.assertEqual(self._count(HardDeleteModel), 1)

        thing.name = "parent2"
        thing_updated = self.soft.save(thing, actor="tester")
        self.assertEqual(thing_updated.name, "parent2")

        thing_updated_2 = self.soft.save(thing_updated, actor="tester2")
        self.assertEqual(thing_updated_2.name, "parent2")

        operations = [a.operation for a in self._audits()]
        self.assertIn("create", operations)
        self.assertIn("update", operations)

    def test_save_new_with_explicit_id_when_missing(self) -> None:
        """Tests save() with explicit id when missing"""
        thing = SoftDeleteModel(id=123, name="ghost")
        thing_out = self.soft.save(thing)
        self.assertEqual(thing_out.id, 123)
        self.assertEqual(self._count(SoftDeleteModel), 1)

    def test_save_with_none_id_routes_to_insert(self) -> None:
        """Tests save() with None id routes to insert"""
        thing = SoftDeleteModel(name="no-id")
        thing_out = self.soft.save(thing)
        self.assertIsNotNone(thing_out.id)
        self.assertEqual(self._count(SoftDeleteModel), 1)

    def test_delete_soft_and_restore(self) -> None:
        """Tests soft delete and restore"""
        thing = self.soft.insert(SoftDeleteModel(name="victim"))
        thing_id = int(thing.id)  # type: ignore[arg-type]

        # Restore early-return (already active) covers branch
        self.assertTrue(self.soft.restore(thing_id, actor="isaac"))

        # Soft delete
        ok = self.soft.delete(thing_id, actor="isaac")
        self.assertTrue(ok)

        # Default listing excludes soft-deleted
        self.assertEqual(len(self.soft.all()), 0)

        # include_deleted shows it
        included = self.soft.all(include_deleted=True)
        self.assertEqual(len(included), 1)
        self.assertIsNotNone(included[0].deleted_at)

        # get() respects include_deleted
        self.assertIsNone(self.soft.get(thing_id))
        self.assertIsNotNone(self.soft.get(thing_id, include_deleted=True))

        # Restore from soft-delete
        restored = self.soft.restore(thing_id, actor="isaac")
        self.assertTrue(restored)
        self.assertEqual(len(self.soft.all()), 1)
        self.assertIsNone(self.soft.get(thing_id).deleted_at)  # type: ignore[union-attr]

        operations = [audit.operation for audit in self._audits()]
        self.assertIn("soft_delete", operations)
        self.assertIn("restore", operations)

    def test_delete_hard(self) -> None:
        """Tests hard delete"""
        h = self.hard.insert(HardDeleteModel(name="gone"))
        hid = int(h.id)  # type: ignore[arg-type]
        ok = self.hard.delete(hid, actor="x")
        self.assertTrue(ok)
        self.assertEqual(self._count(HardDeleteModel), 0)
        operations = [audit.operation for audit in self._audits()]
        self.assertIn("delete", operations)

    def test_batch_insert_and_delete(self) -> None:
        """Tests batch insert and delete"""
        rows = self.soft.insert_many(
            [SoftDeleteModel(name="a"), SoftDeleteModel(name="b")]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(self._count(SoftDeleteModel), 2)

        ids = [int(row.id) for row in rows if row.id is not None]
        # include a bogus id to cover delete_many skip branch
        num_deleted = self.soft.delete_many(ids + [999_999], actor="batch")
        self.assertEqual(num_deleted, len(ids))

        self.assertEqual(len(self.soft.all()), 0)
        self.assertEqual(len(self.soft.all(include_deleted=True)), 2)

    def test_session_reuse_for_reads_and_writes(self) -> None:
        """Tests session reuse for reads and writes"""
        with db.transaction() as session:
            with db.use_session(session):
                # write uses existing session
                thing = self.soft.insert(SoftDeleteModel(name="inside"), actor="x")
                self.assertIsNotNone(thing.id)

                thing.name = "inside2"
                thing_updated = self.soft.save(
                    thing, actor="x"
                )  # still uses existing session
                self.assertEqual(thing_updated.name, "inside2")

                # read uses existing session
                assert thing_updated.id is not None
                self.assertIsNotNone(
                    self.soft.get(int(thing_updated.id))
                )  # _read_session -> existing
                self.assertEqual(len(self.soft.all()), 1)

                # delete uses existing session
                self.assertIsNotNone(thing_updated.id)
                self.assertTrue(self.soft.delete(int(thing_updated.id), actor="x"))

    def test_hook_decorators_coverage(self) -> None:
        """Tests hook decorators coverage"""
        decorators = [
            self.soft.after_insert,
            self.soft.before_update,
            self.soft.after_update,
            self.soft.before_delete,
            self.soft.after_delete,
        ]
        for decorator in decorators:
            result = decorator()
            self.assertTrue(callable(result))

    def test_read_session_without_existing_session(self) -> None:
        """Tests _read_session creates a new session when CURRENT_SESSION is None"""
        thing = self.soft.insert(SoftDeleteModel(name="test"))
        db.CURRENT_SESSION.set(None)  # ensure clear
        assert thing.id is not None
        result = self.soft.get(int(thing.id))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.name, "test")

    def test_all_with_soft_delete_filtering(self) -> None:
        """Tests all with soft delete filtering"""
        thing = self.soft.insert(SoftDeleteModel(name="deleted"))
        assert thing.id is not None
        self.soft.delete(int(thing.id))
        self.assertEqual(len(self.soft.all()), 0)
        self.assertEqual(len(self.soft.all(include_deleted=True)), 1)

    def test_delete_missing_and_restore_on_non_soft_model(self) -> None:
        """Tests delete missing and restore on non-soft model"""
        # delete: obj is None -> False
        self.assertFalse(self.hard.delete(424242))

        # restore: obj exists but model has no deleted_at -> not hasattr(...) branch
        thing = self.hard.insert(HardDeleteModel(name="thing"))
        assert thing.id is not None
        self.assertFalse(self.hard.restore(int(thing.id)))
