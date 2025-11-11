# vention_storage/src/storage/services/database_service.py

from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlmodel import SQLModel, select
from sqlalchemy import desc

from vention_storage.src.storage import database, io_helpers
from vention_storage.src.storage.auditor import AuditLog
from vention_storage.src.storage.utils import Operation
from vention_storage.src.storage.io_helpers import (
    discover_user_tables,
    build_export_zip_bytes,
    db_file_path,
    build_backup_bytes,
    validate_sqlite_file,
    safe_unlink,
)


__all__ = ["DatabaseService", "DatabaseError"]


# ---------------------------------------------------------
# Exceptions (transport-agnostic)
# ---------------------------------------------------------


class DatabaseError(Exception):
    """Base class for database-level service errors."""

    def __init__(self, message: str, code: str = "UNKNOWN"):
        super().__init__(message)
        self.code = code


class DependencyError(DatabaseError):
    def __init__(self, message: str):
        super().__init__(message, code="DEPENDENCY_ERROR")


class ValidationError(DatabaseError):
    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR")


class OperationalError(DatabaseError):
    def __init__(self, message: str):
        super().__init__(message, code="OPERATIONAL_ERROR")


# ---------------------------------------------------------
# Database Service
# ---------------------------------------------------------


class DatabaseService:
    """
    Transport-agnostic database utilities shared between REST and RPC.

    Exposes operations like:
      - health check
      - audit log queries
      - schema diagram (SVG)
      - export.zip / backup.sqlite creation
      - restore.sqlite upload + validation
    """

    def __init__(
        self,
        *,
        audit_default_limit: int = 100,
        audit_max_limit: int = 1000,
    ) -> None:
        self.audit_default_limit = audit_default_limit
        self.audit_max_limit = audit_max_limit

    # ---------------- HEALTH ----------------

    def health(self) -> Dict[str, str]:
        """Verify that a database engine can be initialized."""
        _ = database.get_engine()
        return {"status": "ok"}

    # ---------------- AUDIT LOG ----------------

    def read_audit(
        self,
        *,
        component: Optional[str] = None,
        record_id: Optional[int] = None,
        actor: Optional[str] = None,
        operation: Optional[Operation] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[AuditLog]:
        """
        Query the audit log table with filtering + pagination.
        """
        limit = limit or self.audit_default_limit
        if limit > self.audit_max_limit:
            limit = self.audit_max_limit

        with database.use_session() as session:
            statement = select(AuditLog)
            if component:
                statement = statement.where(AuditLog.component == component)
            if record_id is not None:
                statement = statement.where(AuditLog.record_id == record_id)
            if actor:
                statement = statement.where(AuditLog.actor == actor)
            if operation:
                statement = statement.where(AuditLog.operation == operation)
            if since is not None:
                statement = statement.where(AuditLog.timestamp >= since)
            if until is not None:
                statement = statement.where(AuditLog.timestamp < until)

            statement = (
                statement.order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit)
            )
            results = session.exec(statement).all()
            return list(results)

    # ---------------- DIAGRAM ----------------

    def schema_diagram_svg(self) -> bytes:
        """
        Generate a database schema diagram as SVG bytes.
        Requires `sqlalchemy-schemadisplay` and Graphviz installed.
        """
        try:
            from sqlalchemy_schemadisplay import create_schema_graph
        except Exception as e:
            raise DependencyError(
                "sqlalchemy-schemadisplay is required. Install with: "
                "pip install sqlalchemy-schemadisplay"
            ) from e

        try:
            graph = create_schema_graph(
                engine=database.get_engine(),
                metadata=SQLModel.metadata,
                show_datatypes=True,
                show_indexes=False,
                concentrate=False,
            )
            svg_bytes = graph.create_svg()
            if isinstance(svg_bytes, str):
                return svg_bytes.encode("utf-8")
            return bytes(svg_bytes)
        except Exception as e:
            msg = str(e).lower()
            if "executable" in msg or "dot not found" in msg or "graphviz" in msg:
                raise DependencyError(
                    "Graphviz is required to render the diagram. "
                    "Install it via `brew install graphviz` or `apt-get install graphviz`."
                ) from e
            raise OperationalError(f"Failed to generate schema diagram: {e}") from e

    # ---------------- EXPORT ZIP ----------------

    def export_zip(self) -> bytes:
        """
        Export all user-defined tables as a ZIP archive of CSVs.
        """
        try:
            return build_export_zip_bytes(discover_user_tables())
        except Exception as e:
            raise OperationalError(f"Failed to build export.zip: {e}") from e

    # ---------------- BACKUP SQLITE ----------------

    def backup_sqlite(self) -> Dict[str, Any]:
        """
        Create a consistent SQLite backup and return metadata + bytes.
        """
        path = db_file_path()
        try:
            data = build_backup_bytes(path)
        except Exception as e:
            raise OperationalError(f"Failed to create backup: {e}") from e

        filename = f"backup-{self._timestamp_slug()}.sqlite"
        return {"filename": filename, "data": data}

    # ---------------- RESTORE SQLITE ----------------

    def restore_sqlite(
        self,
        file_bytes: bytes,
        *,
        filename: str = "upload.sqlite",
        integrity_check: bool = True,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Restore a database from raw SQLite bytes.

        Steps:
          1. Save to a temp path
          2. Validate header & integrity
          3. Optionally replace existing DB atomically
        """
        path = db_file_path()
        db_dir = Path(path).resolve().parent

        try:
            tmp_path, total = io_helpers.save_bytes_to_temp(
                file_bytes, db_dir, filename=filename
            )
        except Exception as e:
            raise OperationalError(f"Failed to save upload: {e}") from e

        try:
            validate_sqlite_file(tmp_path, run_integrity_check=integrity_check)
        except ValueError as ve:
            safe_unlink(tmp_path)
            raise ValidationError(str(ve)) from ve
        except Exception as e:
            safe_unlink(tmp_path)
            raise ValidationError(f"Invalid SQLite file: {e}") from e

        if dry_run:
            safe_unlink(tmp_path)
            return {"status": "ok", "restored": False, "bytes": total}

        try:
            io_helpers.atomic_replace_db(tmp_path, Path(path))
        except Exception as e:
            safe_unlink(tmp_path)
            raise OperationalError(f"Failed to replace database file: {e}") from e

        return {"status": "ok", "restored": True, "bytes": total}

    # ---------------- INTERNAL ----------------

    def _timestamp_slug(self) -> str:
        """UTC timestamp safe for filenames."""
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
