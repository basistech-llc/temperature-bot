"""Integration tests for the developer snapshot downloader."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from bin.fetch_database_snapshot import download_snapshot


@dataclass
class SnapshotServerState:
    """Mutable response state shared by a local snapshot test server."""

    body: bytes
    conflict_status: int | None = None
    requests: int = 0
    sha256: str | None = None


@contextmanager
def _snapshot_server(state: SnapshotServerState):
    class Handler(BaseHTTPRequestHandler):
        """Serve a conflict once, then a verified SQLite response."""

        def do_GET(self):  # noqa: N802
            state.requests += 1
            if state.conflict_status is not None and state.requests == 1:
                body = json.dumps(
                    {
                        "code": "conflict",
                        "error": "A database snapshot is already in progress",
                    }
                ).encode()
                self.send_response(state.conflict_status)
                self.send_header("Content-Type", "application/json")
            else:
                body = state.body
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.sqlite3")
                self.send_header("X-Database-Size", str(len(body)))
                self.send_header(
                    "X-Database-SHA256",
                    state.sha256 or hashlib.sha256(body).hexdigest(),
                )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # pylint: disable=redefined-builtin
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/snapshot"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _database_bytes(path: Path) -> bytes:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE readings(value INTEGER NOT NULL)")
        connection.execute("INSERT INTO readings VALUES (42)")
    return path.read_bytes()


@pytest.mark.parametrize("conflict_status", [200, 409])
def test_downloader_waits_for_conflict_then_reports_progress(
    tmp_path, capsys, conflict_status
):
    body = _database_bytes(tmp_path / "source.db")
    state = SnapshotServerState(body=body, conflict_status=conflict_status)
    destination = tmp_path / "downloaded.db"

    with _snapshot_server(state) as url:
        metadata = download_snapshot(
            url,
            destination,
            retry_delay=0,
            wait_timeout=5,
            request_timeout=5,
        )

    output = capsys.readouterr()
    assert state.requests == 2
    assert destination.read_bytes() == body
    assert metadata.sha256 == hashlib.sha256(body).hexdigest()
    assert "Waiting for the server to prepare" in output.out
    assert "snapshot is already in progress" in output.out
    assert "Downloading snapshot [" in output.err
    assert "100%" in output.err


def test_downloader_removes_snapshot_with_bad_checksum(tmp_path):
    body = _database_bytes(tmp_path / "source.db")
    state = SnapshotServerState(body=body, sha256="0" * 64)
    destination = tmp_path / "downloaded.db"

    with _snapshot_server(state) as url:
        with pytest.raises(RuntimeError, match="SHA-256"):
            download_snapshot(url, destination, request_timeout=5)

    assert not destination.exists()
