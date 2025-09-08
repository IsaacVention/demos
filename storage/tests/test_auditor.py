from __future__ import annotations

from datetime import datetime, date

from sqlmodel import Session, select

from storage import database as db
from storage.auditor import AuditLog, audit_operation, _json_default, _jsonify
from storage_tests.fixtures import StorageTestCase, TestModel


class TestAuditor(StorageTestCase):
    def test_create_update_delete_soft_restore_audits(self) -> None:
        """audit_operation logs all CRUD operations with proper before/after state and timestamps."""
        # --- CREATE ---
        with db.transaction() as session:
            thing = TestModel(name="alpha")
            session.add(thing)
            session.flush()
            session.refresh(thing)
            assert thing.id is not None
            audit_operation(
                session=session,
                component="things",
                operation="create",
                record_id=thing.id,
                actor="tester",
                before=None,
                after=thing.model_dump(),
            )

        with Session(self.engine) as session_check:
            logs = session_check.exec(select(AuditLog)).all()
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].component, "things")
            self.assertEqual(logs[0].operation, "create")
            self.assertIsNone(logs[0].before)
            self.assertIsNotNone(logs[0].after)
            self.assertTrue(isinstance(logs[0].timestamp, datetime))

        # --- UPDATE ---
        with db.transaction() as session:
            thing = session.exec(
                select(TestModel).where(TestModel.name == "alpha")
            ).one()
            before = thing.model_dump()
            thing.name = "beta"
            session.add(thing)
            session.flush()
            session.refresh(thing)
            assert thing.id is not None
            audit_operation(
                session=session,
                component="things",
                operation="update",
                record_id=thing.id,
                actor="tester",
                before=before,
                after=thing.model_dump(),
            )

        with Session(self.engine) as session_check2:
            updates = session_check2.exec(
                select(AuditLog).where(AuditLog.operation == "update")
            ).all()
            self.assertEqual(len(updates), 1)
            self.assertEqual(updates[0].before["name"], "alpha")
            self.assertEqual(updates[0].after["name"], "beta")

        # --- SOFT DELETE (we just log) ---
        with db.transaction() as session:
            thing = session.exec(
                select(TestModel).where(TestModel.name == "beta")
            ).one()
            before = thing.model_dump()
            assert thing.id is not None
            audit_operation(
                session=session,
                component="things",
                operation="soft_delete",
                record_id=thing.id,
                actor="tester",
                before=before,
                after={"deleted": True, **thing.model_dump()},
            )

        with Session(self.engine) as session_check3:
            softs = session_check3.exec(
                select(AuditLog).where(AuditLog.operation == "soft_delete")
            ).all()
            self.assertEqual(len(softs), 1)
            self.assertTrue(softs[0].after and softs[0].after.get("deleted"))

        # --- RESTORE (log again) ---
        with db.transaction() as session:
            thing = session.exec(
                select(TestModel).where(TestModel.name == "beta")
            ).one()
            before = {"deleted": True, **thing.model_dump()}
            assert thing.id is not None
            audit_operation(
                session=session,
                component="things",
                operation="restore",
                record_id=thing.id,
                actor="tester",
                before=before,
                after=thing.model_dump(),
            )

        with Session(self.engine) as session_check4:
            restores = session_check4.exec(
                select(AuditLog).where(AuditLog.operation == "restore")
            ).all()
            self.assertEqual(len(restores), 1)
            self.assertTrue(restores[0].before and restores[0].before.get("deleted"))

        # --- DELETE (hard) ---
        with db.transaction() as session:
            thing = session.exec(
                select(TestModel).where(TestModel.name == "beta")
            ).one()
            before = thing.model_dump()
            session.delete(thing)
            assert thing.id is not None
            audit_operation(
                session=session,
                component="things",
                operation="delete",
                record_id=thing.id,
                actor="tester",
                before=before,
                after=None,
            )

        with Session(self.engine) as session_done:
            deletes = session_done.exec(
                select(AuditLog).where(AuditLog.operation == "delete")
            ).all()
            self.assertEqual(len(deletes), 1)

    def test_audit_table_created_and_writable(self) -> None:
        """AuditLog table can be created and written to independently of other models."""
        with Session(self.engine) as session:
            session.add(
                AuditLog(
                    timestamp=datetime.now(),
                    component="smoke",
                    record_id=1,
                    operation="create",
                    actor="tester",
                    before=None,
                    after={"ok": True},
                )
            )
            session.commit()
            rows = session.exec(
                select(AuditLog).where(AuditLog.component == "smoke")
            ).all()
            self.assertEqual(len(rows), 1)

    def test_json_default_handles_datetime_and_date(self) -> None:
        """_json_default converts datetime and date objects to ISO format strings."""
        date_time = datetime(2023, 1, 1, 12, 0, 0)
        result = _json_default(date_time)
        self.assertEqual(result, "2023-01-01T12:00:00")

        test_date = date(2023, 1, 1)
        result = _json_default(test_date)
        self.assertEqual(result, "2023-01-01")

        # Test unsupported type
        with self.assertRaises(TypeError):
            _json_default({"not": "serializable"})

    def test_jsonify_handles_datetime_in_dict(self) -> None:
        """_jsonify properly serializes dictionaries containing datetime objects."""
        from datetime import datetime

        date_time = datetime(2023, 1, 1, 12, 0, 0)
        data = {"timestamp": date_time, "name": "test"}

        result = _jsonify(data)
        self.assertIsNotNone(result)
        if result is not None:
            self.assertEqual(result["timestamp"], "2023-01-01T12:00:00")
            self.assertEqual(result["name"], "test")

        self.assertIsNone(_jsonify(None))
