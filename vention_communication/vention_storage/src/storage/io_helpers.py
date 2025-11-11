from __future__ import annotations

import csv
import io
import sqlite3
import os
import zipfile
import tempfile
from pathlib import Path
from typing import List

from sqlalchemy import select
from sqlalchemy.sql.schema import Table
from sqlmodel import Session, SQLModel
from vention_storage.src.storage import database
from vention_storage.src.storage.utils import to_primitive
from fastapi import UploadFile

_SQLITE_INTERNAL_PREFIX = "sqlite_"

__all__ = [
    "discover_user_tables",
    "write_table_csv_buffer",
    "build_export_zip_bytes",
    "db_file_path",
    "build_backup_bytes",
    "validate_sqlite_file",
    "save_bytes_to_temp",
    "safe_unlink",
]

# ---------- Table discovery & CSV ----------


def discover_user_tables() -> List[Table]:
    """Return user tables (excludes SQLite internal)."""
    user_tables: List[Table] = []
    for table in SQLModel.metadata.sorted_tables:
        if not table.name.startswith(_SQLITE_INTERNAL_PREFIX):
            user_tables.append(table)
    return user_tables


def write_table_csv_buffer(session: Session, table: Table) -> io.StringIO:
    """SELECT * and return CSV (header + rows) in a StringIO."""
    buffer = io.StringIO(newline="")
    columns = list(table.columns)
    writer = csv.DictWriter(
        buffer, fieldnames=[column.name for column in columns], extrasaction="ignore"
    )
    writer.writeheader()
    result = session.exec(select(table))
    for row in result:
        writer.writerow(
            {column.name: to_primitive(row._mapping[column]) for column in columns}
        )
    return buffer


def build_export_zip_bytes(tables: list[Table]) -> bytes:
    """Return ZIP bytes with one CSV per table (valid empty ZIP if none)."""
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        if tables:
            with database.use_session() as session:
                for table in tables:
                    try:
                        csv_buffer = write_table_csv_buffer(session, table)
                    except Exception as inner:  # surface table context upstream
                        raise RuntimeError(f"table={table.name}: {inner}") from inner
                    zip_file.writestr(f"{table.name}.csv", csv_buffer.getvalue())
    return mem.getvalue()


# ---------- Backup ----------


def db_file_path() -> str:
    """Return absolute DB file path."""
    engine = database.get_engine()
    db_path = engine.url.database or ""
    return str(Path(db_path).resolve())


def build_backup_bytes(db_path: str) -> bytes:
    """
    Build a consistent .sqlite backup and return bytes.
    """
    db_dir = Path(db_path).resolve().parent
    with tempfile.NamedTemporaryFile(
        prefix="backup-", suffix=".sqlite", dir=db_dir, delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        database.get_engine().dispose()
        with (
            sqlite3.connect(str(Path(db_path))) as db_connection,
            sqlite3.connect(str(tmp_path)) as tmp_connection,
        ):
            db_connection.backup(tmp_connection)

        return tmp_path.read_bytes()
    finally:
        safe_unlink(tmp_path)


# ---------- Restore helpers ----------


def validate_sqlite_file(path: Path, *, run_integrity_check: bool = True) -> None:
    """Raise ValueError on validation failure; returns None on success."""
    # Header check
    try:
        with path.open("rb") as file:
            signature = file.read(16)
    except Exception as e:
        raise ValueError(f"Cannot read uploaded file: {e}") from e
    if signature != b"SQLite format 3\x00":
        raise ValueError("Invalid SQLite header")

    if not run_integrity_check:
        return

    # integrity_check
    try:
        uri = f"file:{path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            row = connection.execute("PRAGMA integrity_check;").fetchone()
            ok = row and str(row[0]).lower() == "ok"
            if not ok:
                raise ValueError(
                    f"Integrity check failed: {row[0] if row else 'unknown'}"
                )
        finally:
            connection.close()
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Integrity check error: {e}") from e


def save_upload_to_temp(file: UploadFile, dest_dir: Path) -> tuple[Path, int]:
    with tempfile.NamedTemporaryFile(
        prefix="restore-", suffix=".sqlite", dir=dest_dir, delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
        total = 0
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            tmp.write(chunk)
            total += len(chunk)
    try:
        file.file.close()
    except Exception:
        pass
    return tmp_path, total


def save_bytes_to_temp(
    file_bytes: bytes, dest_dir: Path, *, filename: str = "upload.sqlite"
) -> tuple[Path, int]:
    """Save bytes to a temporary file in the destination directory."""
    with tempfile.NamedTemporaryFile(
        prefix="restore-", suffix=".sqlite", dir=dest_dir, delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(file_bytes)
        total = len(file_bytes)
    return tmp_path, total


def atomic_replace_db(tmp_path: Path, db_path: Path) -> None:
    database.get_engine().dispose()
    os.replace(str(tmp_path), str(db_path))


def safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass
