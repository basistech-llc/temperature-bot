"""Tests for the FCU mode control endpoint."""

import json
import os
import sqlite3
import time

from app import ae200
from app import db

BROADWAY_SOUTH = 10


def _connect_test_db():
    conn = sqlite3.connect(os.environ["TEST_DB_NAME"])
    conn.row_factory = sqlite3.Row
    return conn


def _link_device_to_unit(name):
    conn = _connect_test_db()
    try:
        device_id = db.get_or_create_device_id(conn, name)
        conn.execute(
            "UPDATE devices SET ae200_device_id=? WHERE device_id=?",
            (BROADWAY_SOUTH, device_id),
        )
        conn.commit()
        return device_id
    finally:
        conn.close()


def test_set_mode_endpoint_records_mode_and_disables_rules(flask_test_client):  # noqa: F811
    """Manual FCU mode changes should update simulator status and local logs."""
    target_mode = "HEAT"
    original_mode = ae200.get_device_info(BROADWAY_SOUTH).get(ae200.AE200_MODE_KEY)
    device_id = _link_device_to_unit("Broadway Mode Test")
    ae200.set_mode(BROADWAY_SOUTH, "COOL")

    conn = _connect_test_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS n FROM changelog WHERE device_id=?", (device_id,))
    before_changelog = cursor.fetchone()["n"]
    cursor.execute("SELECT COUNT(*) AS n FROM devlog WHERE device_id=?", (device_id,))
    before_devlog = cursor.fetchone()["n"]
    conn.close()

    now = int(time.time())
    try:
        response = flask_test_client.post(
            "/api/v1/set_mode",
            json={"device_id": device_id, "mode": target_mode},
        )
        assert response.status_code == 200
        assert response.json["status"] == "ok"
        assert response.json["device_id"] == device_id
        assert str(response.json["unit"]) == str(BROADWAY_SOUTH)
        assert response.json["mode"] == target_mode
        assert ae200.get_device_info(BROADWAY_SOUTH)[ae200.AE200_MODE_KEY] == target_mode

        verify_conn = _connect_test_db()
        verify_cursor = verify_conn.cursor()
        verify_cursor.execute(
            "SELECT disabled_until FROM devices WHERE device_id=?", (device_id,)
        )
        assert verify_cursor.fetchone()["disabled_until"] >= now + 60
        verify_cursor.execute(
            "SELECT COUNT(*) AS n FROM devlog WHERE device_id=?", (device_id,)
        )
        assert verify_cursor.fetchone()["n"] == before_devlog + 1
        verify_cursor.execute(
            "SELECT status_json FROM devlog WHERE device_id=? ORDER BY logtime DESC",
            (device_id,),
        )
        status = json.loads(verify_cursor.fetchone()["status_json"])
        assert status[ae200.AE200_MODE_KEY] == target_mode
        verify_cursor.execute(
            "SELECT COUNT(*) AS n FROM changelog WHERE device_id=?", (device_id,)
        )
        assert verify_cursor.fetchone()["n"] >= before_changelog + 2
        verify_conn.close()
    finally:
        if original_mode in ae200.AE200_ALLOWED_SET_MODES:
            ae200.set_mode(BROADWAY_SOUTH, original_mode)


def test_set_mode_endpoint_rejects_invalid_mode(flask_test_client):  # noqa: F811
    device_id = _link_device_to_unit("Broadway Invalid Mode Test")

    response = flask_test_client.post(
        "/api/v1/set_mode",
        json={"device_id": device_id, "mode": "AUTO"},
    )

    assert response.status_code == 400
