"""Integration tests for consistent database snapshot downloads."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from pathlib import Path

from app.database_snapshot import create_database_snapshot
from app.instance_policy import InstancePolicy, load_policy_table


def test_snapshot_includes_committed_wal_data(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        connection.execute("CREATE TABLE readings(value INTEGER NOT NULL)")
        connection.execute("INSERT INTO readings VALUES (42)")
        connection.commit()
        snapshot = create_database_snapshot(source)

    try:
        with sqlite3.connect(snapshot.path) as downloaded:
            assert downloaded.execute("SELECT value FROM readings").fetchall() == [(42,)]
            assert downloaded.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert snapshot.size == snapshot.path.stat().st_size
        assert snapshot.sha256 == hashlib.sha256(snapshot.path.read_bytes()).hexdigest()
    finally:
        snapshot.path.unlink(missing_ok=True)


def test_production_snapshot_endpoint_returns_verified_sqlite(
    flask_test_client, test_database_conn_with_test_data, tmp_path
):
    connection, _device_id, _counts = test_database_conn_with_test_data
    source = tmp_path / "production.db"
    with sqlite3.connect(source) as destination:
        connection.backup(destination)
    definition = load_policy_table().for_instance("production")
    policy = InstancePolicy(
        instance=definition.name,
        role=definition.role,
        control_mode=definition.control_mode,
        database_identity=definition.database_identity,
        database_path=source,
        private_database=definition.private_database,
        scheduler_mode=definition.scheduler_mode,
        integrations=definition.integrations,
    )
    application = flask_test_client.application
    previous = application.config["INSTANCE_POLICY"]
    application.config["INSTANCE_POLICY"] = policy
    snapshots_before = set(
        Path(tempfile.gettempdir()).glob("temperature-bot-*.db")
    )
    try:
        response = flask_test_client.get(
            "/api/v1/database-snapshot", buffered=False
        )
    finally:
        application.config["INSTANCE_POLICY"] = previous

    snapshots = set(
        Path(tempfile.gettempdir()).glob("temperature-bot-*.db")
    ) - snapshots_before
    assert len(snapshots) == 1
    snapshot_path = snapshots.pop()

    assert response.status_code == 200
    assert response.headers["Content-Disposition"].endswith(
        'filename=temperature-bot.db'
    )
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Database-Size"] == str(len(response.data))
    assert response.headers["X-Database-SHA256"] == hashlib.sha256(
        response.data
    ).hexdigest()
    downloaded = tmp_path / "downloaded.db"
    downloaded.write_bytes(response.data)
    with sqlite3.connect(downloaded) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert connection.execute("SELECT count(*) FROM devices").fetchone()[0] > 0
    try:
        response.close()
        assert not snapshot_path.exists()
    finally:
        snapshot_path.unlink(missing_ok=True)


def test_nonproduction_snapshot_endpoint_is_not_exposed(flask_test_client):
    response = flask_test_client.get("/api/v1/database-snapshot")

    assert response.status_code == 404
    assert response.json["code"] == "not_found"
