from __future__ import annotations

import importlib
import tempfile
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, select
from storage_tests.fixtures import StorageTestCase, Parent, Child
from storage import database


class TestDatabase(StorageTestCase):
    def test_set_database_url_before_engine_singleton_and_pragma(self) -> None:
        """set_database_url configures engine before creation; engine is singleton; SQLite foreign keys enabled."""
        importlib.reload(database)
        with tempfile.TemporaryDirectory() as temp_dir:
            url = self._sqlite_url(Path(temp_dir))
            database.set_database_url(url)
            engine1 = database.get_engine()
            engine2 = database.get_engine()
            self.assertIs(engine1, engine2, "engine must be a singleton")

            with Session(engine1) as session:
                value = session.exec(text("PRAGMA foreign_keys")).one()[0]
                self.assertEqual(
                    value, 1, "SQLite foreign_keys pragma should be enabled"
                )

            SQLModel.metadata.create_all(engine1)

    def test_set_database_url_after_engine_raises(self) -> None:
        """set_database_url raises RuntimeError if called after engine initialization."""
        importlib.reload(database)
        with tempfile.TemporaryDirectory() as temp_dir:
            url = self._sqlite_url(Path(temp_dir))
            database.set_database_url(url)
            _ = database.get_engine()
            with self.assertRaises(RuntimeError):
                database.set_database_url(self._sqlite_url(Path(temp_dir)))

    def test_transaction_commit_rollback_and_fk_enforcement(self) -> None:
        """transaction commits on success, rolls back on error, and enforces foreign key constraints."""
        importlib.reload(database)
        with tempfile.TemporaryDirectory() as temp_dir:
            url = self._sqlite_url(Path(temp_dir))
            database.set_database_url(url)
            engine = database.get_engine()
            SQLModel.metadata.create_all(engine)

            # --- commit path (parent + valid child)
            with database.transaction() as session1:
                p = Parent(name="P1")
                session1.add(p)
                session1.flush()
                session1.refresh(p)
                assert p.id is not None
                c = Child(parent_id=p.id, name="C1")
                session1.add(c)

            with Session(engine) as session_check:
                self.assertEqual(len(session_check.exec(select(Parent)).all()), 1)
                self.assertEqual(len(session_check.exec(select(Child)).all()), 1)

            # --- FK enforcement on insert (invalid parent_id)
            with self.assertRaises(IntegrityError):
                with database.transaction() as session2:
                    session2.add(Child(parent_id=999999, name="bad"))  # invalid FK

            # --- rollback path (explicit exception)
            try:
                with database.transaction() as session3:
                    session3.add(Parent(name="WILL_ROLLBACK"))
                    raise RuntimeError("boom")
            except RuntimeError:
                pass

            with Session(engine) as session_check2:
                rows = session_check2.exec(
                    select(Parent).where(Parent.name == "WILL_ROLLBACK")
                ).all()
                self.assertEqual(len(rows), 0)

            # --- FK enforcement on delete (parent blocked by existing child)
            with self.assertRaises(IntegrityError):
                with database.transaction() as session4:
                    parent = session4.exec(
                        select(Parent).where(Parent.name == "P1")
                    ).one()
                    session4.delete(parent)

    def test_attach_sqlite_pragmas_early_return_branch(self) -> None:
        """_attach_sqlite_pragmas returns early for non-SQLite URLs without attaching pragmas."""
        importlib.reload(database)
        with tempfile.TemporaryDirectory() as temp_dir:
            url = self._sqlite_url(Path(temp_dir))
            database.set_database_url(url)
            _ = database.get_engine()

            original = database._DATABASE_URL
            try:
                database._DATABASE_URL = "postgresql://example"
                database._attach_sqlite_pragmas(database.get_engine())
            finally:
                database._DATABASE_URL = original

    def test_use_session_context_manager(self) -> None:
        """use_session sets and resets the current session context variable for both provided and created sessions."""
        importlib.reload(database)
        with tempfile.TemporaryDirectory() as temp_dir:
            url = self._sqlite_url(Path(temp_dir))
            database.set_database_url(url)
            engine = database.get_engine()

            # Test with provided session
            with Session(engine) as session:
                # Initially no current session
                self.assertIsNone(database.CURRENT_SESSION.get())

                # Use the session context with provided session
                with database.use_session(session) as used_session:
                    # Current session should be set
                    self.assertIs(database.CURRENT_SESSION.get(), session)
                    # Should yield the provided session
                    self.assertIs(used_session, session)

                # After context, should be reset to None
                self.assertIsNone(database.CURRENT_SESSION.get())

            # Test without provided session (creates new session)
            # Initially no current session
            self.assertIsNone(database.CURRENT_SESSION.get())

            # Use the session context without providing session
            with database.use_session() as created_session:
                # Current session should be set
                current_session = database.CURRENT_SESSION.get()
                self.assertIsNotNone(current_session)
                # Should yield the created session
                self.assertIs(created_session, current_session)

            # After context, should be reset to None
            self.assertIsNone(database.CURRENT_SESSION.get())
