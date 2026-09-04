"""Create consistent, disposable SQLite snapshots for developer downloads."""

from __future__ import annotations

import fcntl
import hashlib
import sqlite3
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class SnapshotBusy(RuntimeError):
    """Another worker is already creating a snapshot of this database."""


class DatabaseSnapshot(BaseModel):
    """Verified temporary SQLite snapshot and its response metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: Path
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _lock_path(source: Path) -> Path:
    identity = hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"temperature-bot-snapshot-{identity}.lock"


def create_database_snapshot(source: Path) -> DatabaseSnapshot:
    """Return a consistent backup of *source*, including committed WAL data."""
    if not source.is_file():
        raise FileNotFoundError(f"database does not exist: {source}")
    with _lock_path(source).open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SnapshotBusy("a database snapshot is already in progress") from error

        with tempfile.NamedTemporaryFile(
            prefix="temperature-bot-", suffix=".db", delete=False
        ) as stream:
            snapshot = Path(stream.name)
        try:
            snapshot.chmod(0o600)
            source_uri = source.resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(source_uri, uri=True, timeout=30) as source_conn:
                with sqlite3.connect(snapshot) as snapshot_conn:
                    source_conn.backup(snapshot_conn, pages=4096, sleep=0.05)
                    result = snapshot_conn.execute("PRAGMA quick_check").fetchone()
                    if result != ("ok",):
                        raise sqlite3.DatabaseError("snapshot failed SQLite quick_check")
            return DatabaseSnapshot(
                path=snapshot,
                size=snapshot.stat().st_size,
                sha256=_sha256(snapshot),
            )
        except Exception:
            snapshot.unlink(missing_ok=True)
            raise
