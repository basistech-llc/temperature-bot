"""Tests for the FCU mode control endpoint."""

import json
import os
import sqlite3
import time

import pytest

from app import ae200
from app import db

BROADWAY_SOUTH = 10
AREA_51 = 11
STALE_AREA_51_UNIT = 2
BAMBOO_PRODUCTION_UNIT = 7


def _connect_test_db():
    conn = sqlite3.connect(os.environ["TEST_DB_NAME"])
    conn.row_factory = sqlite3.Row
    return conn


def _link_device_to_unit(name, ae200_unit=BROADWAY_SOUTH):
    conn = _connect_test_db()
    try:
        device_id = db.get_or_create_device_id(conn, name)
        conn.execute(
            "UPDATE devices SET ae200_device_id=? WHERE device_id=?",
            (ae200_unit, device_id),
        )
        conn.commit()
        return device_id
    finally:
        conn.close()


def _seed_ae200_status(device_id, status):
    conn = _connect_test_db()
    try:
        db.insert_devlog_entry(
            conn,
            device_id=device_id,
            temp=status.get("InletTemp"),
            statusdict=status,
            force=True,
        )
    finally:
        conn.close()


def test_set_auto_temp_endpoint_updates_dual_setpoints(flask_test_client):  # noqa: F811
    """Auto mode setpoint edits should write AE-200 Heat and Cool values."""
    device_id = _link_device_to_unit("Broadway Auto SetTemp Test")
    original_status = ae200.get_device_info(BROADWAY_SOUTH)
    original_heat = original_status.get(ae200.AE200_HEAT_SET_TEMP_KEY)
    original_cool = original_status.get(ae200.AE200_COOL_SET_TEMP_KEY)

    try:
        ae200.set_auto_set_temps(
            BROADWAY_SOUTH,
            heat_set_temp_c=19.0,
            cool_set_temp_c=24.0,
        )

        response = flask_test_client.post(
            "/api/v1/set_auto_temp",
            json={
                "device_id": device_id,
                "heat_set_temp_c": 20.0,
                "cool_set_temp_c": 25.0,
            },
        )
        assert response.status_code == 200
        assert response.json["status"] == "ok"
        assert response.json["device_id"] == device_id
        assert str(response.json["unit"]) == str(BROADWAY_SOUTH)
        assert response.json["heat_set_temp_c"] == pytest.approx(20.0)
        assert response.json["cool_set_temp_c"] == pytest.approx(25.0)

        device_info = ae200.get_device_info(BROADWAY_SOUTH)
        assert device_info[ae200.AE200_HEAT_SET_TEMP_KEY] == "20.0"
        assert device_info[ae200.AE200_COOL_SET_TEMP_KEY] == "25.0"

        conn = _connect_test_db()
        try:
            row = conn.execute(
                "SELECT status_json FROM devlog WHERE device_id=? ORDER BY logtime DESC",
                (device_id,),
            ).fetchone()
            status = json.loads(row["status_json"])
            assert status[ae200.AE200_HEAT_SET_TEMP_KEY] == "20.0"
            assert status[ae200.AE200_COOL_SET_TEMP_KEY] == "25.0"
        finally:
            conn.close()
    finally:
        if original_heat is not None and original_cool is not None:
            ae200.set_auto_set_temps(
                BROADWAY_SOUTH,
                heat_set_temp_c=original_heat,
                cool_set_temp_c=original_cool,
            )


def test_set_mode_endpoint_records_mode_and_disables_rules(flask_test_client):  # noqa: F811
    """Manual FCU mode changes should update simulator status and local logs."""
    target_mode = "AUTO"
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
        assert status[ae200.AE200_COOL_SET_TEMP_KEY] == "24"
        assert status[ae200.AE200_HEAT_SET_TEMP_KEY] == "19"
        verify_cursor.execute(
            "SELECT COUNT(*) AS n FROM changelog WHERE device_id=?", (device_id,)
        )
        assert verify_cursor.fetchone()["n"] >= before_changelog + 2
        verify_cursor.execute(
            """
            SELECT comment FROM changelog
            WHERE device_id=? AND comment='Rules disabled for 180 minutes'
            ORDER BY changelog_id DESC
            LIMIT 1
            """,
            (device_id,),
        )
        assert verify_cursor.fetchone()["comment"] == "Rules disabled for 180 minutes"
        verify_conn.close()
    finally:
        if original_mode in ae200.AE200_ALLOWED_SET_MODES:
            ae200.set_mode(BROADWAY_SOUTH, original_mode)


def test_set_mode_endpoint_maps_stale_simulator_unit_by_device_name(
    flask_test_client,
):  # noqa: F811
    """Simulator mode should tolerate local DB IDs that only exist in production."""
    target_mode = "COOL"
    original_mode = ae200.get_device_info(AREA_51).get(ae200.AE200_MODE_KEY)
    device_id = _link_device_to_unit("Area 51", STALE_AREA_51_UNIT)
    ae200.set_mode(AREA_51, "FAN")

    try:
        response = flask_test_client.post(
            "/api/v1/set_mode",
            json={"device_id": device_id, "mode": target_mode},
        )

        assert response.status_code == 200
        assert response.json["status"] == "ok"
        assert response.json["device_id"] == device_id
        assert str(response.json["unit"]) == str(AREA_51)
        assert response.json["mode"] == target_mode
        assert ae200.get_device_info(AREA_51)[ae200.AE200_MODE_KEY] == target_mode
    finally:
        if original_mode in ae200.AE200_ALLOWED_SET_MODES:
            ae200.set_mode(AREA_51, original_mode)


def test_set_mode_endpoint_registers_db_backed_simulator_unit(
    flask_test_client,
):  # noqa: F811
    """Local simulator should control DB-backed production units absent from fixtures."""
    target_mode = "FAN"
    device_id = _link_device_to_unit("Bamboo", BAMBOO_PRODUCTION_UNIT)
    _seed_ae200_status(
        device_id,
        {
            "Drive": "OFF",
            "FanSpeed": "AUTO",
            "Mode": "COOL",
            "SetTemp": "26",
            "InletTemp": "27.6",
        },
    )

    response = flask_test_client.post(
        "/api/v1/set_mode",
        json={"device_id": device_id, "mode": target_mode},
    )

    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["device_id"] == device_id
    assert str(response.json["unit"]) == str(BAMBOO_PRODUCTION_UNIT)
    assert response.json["mode"] == target_mode
    assert (
        ae200.get_device_info(BAMBOO_PRODUCTION_UNIT)[ae200.AE200_MODE_KEY]
        == target_mode
    )


def test_set_mode_endpoint_rejects_unmapped_simulator_unit(flask_test_client):  # noqa: F811
    device_id = _link_device_to_unit("Missing Simulator Unit", STALE_AREA_51_UNIT)

    response = flask_test_client.post(
        "/api/v1/set_mode",
        json={"device_id": device_id, "mode": "COOL"},
    )

    assert response.status_code == 400
    assert response.json == {"error": "Invalid command request"}
    assert "Missing Simulator Unit" not in response.get_data(as_text=True)


def test_set_mode_endpoint_rejects_invalid_mode(flask_test_client):  # noqa: F811
    device_id = _link_device_to_unit("Broadway Invalid Mode Test")

    response = flask_test_client.post(
        "/api/v1/set_mode",
        json={"device_id": device_id, "mode": "SETBACK"},
    )

    assert response.status_code == 400
