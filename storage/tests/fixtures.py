from __future__ import annotations

import importlib
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlmodel import Field, SQLModel, Session

from storage import database as db


# --- Shared Test Models ------------------------------------------------------


class TestModel(SQLModel, table=True):  # type: ignore[misc, call-arg]
    """Basic test model for general testing."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class SoftDeleteModel(SQLModel, table=True):  # type: ignore[misc, call-arg]
    """Test model with soft delete capability."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    deleted_at: Optional[datetime] = Field(default=None, index=True)


class HardDeleteModel(SQLModel, table=True):  # type: ignore[misc, call-arg]
    """Test model without soft delete capability."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class Parent(SQLModel, table=True):  # type: ignore[misc, call-arg]
    """Test model for foreign key relationships."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class Child(SQLModel, table=True):  # type: ignore[misc, call-arg]
    """Test model with foreign key to Parent."""

    id: Optional[int] = Field(default=None, primary_key=True)
    parent_id: int = Field(foreign_key="parent.id")
    name: str


# --- Shared Test Base Class --------------------------------------------------


class StorageTestCase(unittest.TestCase):
    """Base test case with common setup for storage tests."""

    def setUp(self) -> None:
        """Set up fresh database for each test."""
        # Reload the database module
        importlib.reload(db)

        self._temp_dir = tempfile.TemporaryDirectory()
        url = self._sqlite_url(Path(self._temp_dir.name))
        db.set_database_url(url)
        engine = db.get_engine()

        # Create all tables including AuditLog
        SQLModel.metadata.create_all(engine)
        self.engine = engine

    def tearDown(self) -> None:
        """Clean up temporary directory."""
        self._temp_dir.cleanup()

    def _sqlite_url(self, tmpdir: Path) -> str:
        """Create SQLite URL for test database."""
        return (
            f"sqlite:///{(tmpdir / f'{self.__class__.__name__}_tests.db').as_posix()}"
        )

    def _create_session(self) -> Session:
        """Create a new database session."""
        return Session(self.engine)
