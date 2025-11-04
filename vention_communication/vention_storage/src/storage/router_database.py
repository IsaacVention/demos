from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile, File
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

__all__ = ["build_db_router"]


def build_db_router(
    *,
    audit_default_limit: int = 100,
    audit_max_limit: int = 1000,
) -> APIRouter:
    """
    Build a FastAPI router exposing database-wide utilities.

    Endpoints:
      - /db/health          : Verify DB engine is available
      - /db/audit           : Query audit logs (filters + pagination)
      - /db/diagram.svg     : Schema diagram (requires Graphviz)
      - /db/export.zip      : CSV export (one CSV per table)
      - /db/backup.sqlite   : Full SQLite backup file
      - /db/restore         : Upload and restore a .sqlite backup (atomic replace)
    """
    router = APIRouter(prefix="/db", tags=["db"])

    @router.get("/health")
    def health() -> Dict[str, str]:
        """
        Check database connectivity.

        Returns:
            dict: {"status": "ok"} if the database engine can be initialized.
        """
        _ = database.get_engine()
        return {"status": "ok"}

    @router.get("/audit")
    def read_audit(
        component: Optional[str] = Query(None, description="Filter by component name"),
        record_id: Optional[int] = Query(None, description="Filter by record ID"),
        actor: Optional[str] = Query(None, description="Filter by actor identifier"),
        operation: Optional[Operation] = Query(
            None, description="Filter by operation type"
        ),
        since: Optional[datetime] = Query(
            None, description="Include only logs on/after this timestamp"
        ),
        until: Optional[datetime] = Query(
            None, description="Include only logs before this timestamp"
        ),
        limit: int = Query(
            audit_default_limit,
            ge=1,
            le=audit_max_limit,
            description="Maximum rows to return",
        ),
        offset: int = Query(
            0, ge=0, description="Number of rows to skip (for pagination)"
        ),
    ) -> List[AuditLog]:
        """
        Query the audit log table.

        Supports filtering by component, record_id, actor, operation,
        and timestamp range, with pagination.

        Args:
            component (str, optional): Restrict to a specific component.
            record_id (int, optional): Restrict to a specific record ID.
            actor (str, optional): Restrict to a specific actor (user/system).
            operation (Operation, optional): Restrict to a specific operation.
            since (datetime, optional): Include only logs since this timestamp.
            until (datetime, optional): Include only logs before this timestamp.
            limit (int): Maximum number of logs to return (bounded by audit_max_limit).
            offset (int): Number of rows to skip for pagination.

        Returns:
            List[AuditLog]: A list of audit log entries matching the criteria.
        """
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
            rows: List[AuditLog] = session.exec(statement).all()
            return rows

    @router.get("/diagram.svg", response_class=Response)
    def diagram_svg() -> Response:
        """
        Generate a database schema diagram in SVG format.

        Requires `sqlalchemy-schemadisplay` and Graphviz to be installed.
        The diagram reflects the current SQLModel metadata.

        Returns:
            Response: SVG image of the database schema.

        Raises:
            HTTPException 503: If required dependencies are missing
                               or Graphviz is not available.
        """
        try:
            # import here to avoid hard dependency if not used
            from sqlalchemy_schemadisplay import create_schema_graph
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=(
                    "sqlalchemy-schemadisplay is required. "
                    "Install with: pip install sqlalchemy-schemadisplay"
                ),
            ) from e

        try:
            graph = create_schema_graph(
                engine=database.get_engine(),
                metadata=SQLModel.metadata,
                show_datatypes=True,
                show_indexes=False,
                concentrate=False,
            )
            return Response(content=graph.create_svg(), media_type="image/svg+xml")
        except Exception as e:
            msg = str(e).lower()
            if "executable" in msg or "dot not found" in msg or "graphviz" in msg:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Graphviz is required to render the diagram. "
                        "Install it (e.g. brew install graphviz / apt-get install graphviz)."
                    ),
                ) from e
            raise

    @router.get("/export.zip")
    def export_zip() -> Response:
        """
        Export the entire database as a ZIP archive.

        The archive contains one CSV file per user-defined table found in SQLModel metadata.
        SQLite internal tables (e.g., "sqlite_sequence") are excluded.

        Returns:
            Response: application/zip payload with "{table}.csv" entries.
        """
        headers = {"Content-Disposition": 'attachment; filename="export.zip"'}
        try:
            zip_bytes = build_export_zip_bytes(discover_user_tables())
        except Exception as e:
            raise HTTPException(
                status_code=503, detail=f"Failed to build export.zip: {e}"
            ) from e
        return Response(
            content=zip_bytes, media_type="application/zip", headers=headers
        )

    @router.get("/backup.sqlite")
    def backup_sqlite() -> Response:
        """
        Create and return a consistent SQLite backup of the current database file.

        Uses the SQLite Backup API for correctness.

        Returns:
            Response: application/x-sqlite3 payload with a `.sqlite` file.

        Raises:
            HTTPException 503: Operational failure creating the backup.
        """
        path = db_file_path()
        headers = {
            "Content-Disposition": f'attachment; filename="backup-{_backup_timestamp_slug()}.sqlite"'
        }
        try:
            data = build_backup_bytes(path)
        except Exception as e:
            raise HTTPException(
                status_code=503, detail=f"Failed to create backup: {e}"
            ) from e
        return Response(
            content=data, media_type="application/x-sqlite3", headers=headers
        )

    @router.post("/restore")
    def restore_sqlite(
        file: UploadFile = File(..., description="SQLite .sqlite backup to restore"),
        integrity_check: bool = Query(
            True, description="Run PRAGMA integrity_check before replacing"
        ),
        dry_run: bool = Query(
            False, description="Validate only; do not modify current database"
        ),
    ) -> Dict[str, object]:
        """
        Restore the database from an uploaded SQLite file by atomically replacing the current DB file.

        Steps:
          1. Save upload to a temporary path.
          2. Validate header and (optionally) PRAGMA integrity_check.
          3. If dry_run: report validation OK and exit.
          4. Dispose engine connections and os.replace(temp, db_path).

        Returns:
            dict: {status: "ok", restored: bool, bytes: int}

        Raises:
            HTTPException 422: Invalid SQLite file or failed integrity check.
            HTTPException 503: Operational failure during file I/O.
        """
        path = db_file_path()
        db_dir = Path(path).resolve().parent
        try:
            tmp_path, total = io_helpers.save_upload_to_temp(file, db_dir)
        except Exception as e:
            raise HTTPException(503, f"Failed to save upload: {e}") from e

        try:
            validate_sqlite_file(tmp_path, run_integrity_check=integrity_check)
        except ValueError as ve:
            safe_unlink(tmp_path)
            raise HTTPException(422, str(ve)) from ve
        except Exception as e:
            safe_unlink(tmp_path)
            raise HTTPException(422, f"Invalid SQLite file: {e}") from e

        if dry_run:
            safe_unlink(tmp_path)
            return {"status": "ok", "restored": False, "bytes": total}

        try:
            io_helpers.atomic_replace_db(tmp_path, Path(path))
        except Exception as e:
            safe_unlink(tmp_path)
            raise HTTPException(503, f"Failed to replace database file: {e}") from e

        return {"status": "ok", "restored": True, "bytes": total}

    return router


def _backup_timestamp_slug() -> str:
    """Timestamp safe for filenames (UTC, no colons)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
