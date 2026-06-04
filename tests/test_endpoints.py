"""
test Flask endpoints
"""

import logging
import sqlite3
import os
import json
import time
from unittest.mock import patch

import pytest
from conftest import flask_test_client, skip_on_github  # noqa: F401  # pylint: disable=unused-import
from helpers.data_factories import DeviceTestData
from helpers.mock_helpers import MockHelper

from app import ae200
from app import db
from app import rules_engine
from app.constants import __version__

logger = logging.getLogger(__name__)


def test_get_version(flask_test_client):  # noqa: F811
    response = flask_test_client.get("/version")
    assert response.status_code == 200
    assert response.data.decode("utf-8") == f"version: {__version__}"

    response = flask_test_client.get("/api/v1/version")
    assert response.status_code == 200
    assert response.json == {"version": __version__}


def test_status_endpoint(flask_test_client):  # noqa: F811
    response = flask_test_client.get("/api/v1/status")
    assert response.status_code == 200
    response_json = response.json
    logging.info(" /status: %s", response_json)
    assert "devices" in response_json


def test_metric_endpoint_accepts_known_metrics(flask_test_client):  # noqa: F811
    """/api/v1/metric returns a series payload for each supported AQ metric."""
    for metric in ("humidity", "co2", "voc", "radon", "pm25", "pm1", "pressure"):
        response = flask_test_client.get(f"/api/v1/metric?metric={metric}")
        assert response.status_code == 200, f"metric={metric} status={response.status_code}"
        assert "series" in response.json


def test_metric_endpoint_rejects_unknown_metric(flask_test_client):  # noqa: F811
    response = flask_test_client.get("/api/v1/metric?metric=bogus")
    assert response.status_code == 400


def test_metric_endpoint_rejects_invalid_device_ids(flask_test_client):  # noqa: F811
    """Unparseable device_ids must be rejected with 400, not silently ignored.

    A 200 with all devices in the response would mask a typo in a caller's
    URL and return the wrong data.
    """
    response = flask_test_client.get("/api/v1/metric?metric=co2&device_ids=not-a-number")
    assert response.status_code == 400


def test_metric_chart_page_renders(flask_test_client):  # noqa: F811
    """Every entry in METRIC_CHART_CONFIG must actually render.

    Loops all seven metrics so a typo or missing field in one config entry
    fails loudly instead of silently when users click that metric's cell.
    """
    for metric in ("humidity", "co2", "voc", "radon", "pm25", "pm1", "pressure"):
        response = flask_test_client.get(f"/metric_chart?metric={metric}")
        assert response.status_code == 200, f"metric={metric} status={response.status_code}"
        assert b"METRIC_CHART_CONFIG" in response.data

    response = flask_test_client.get("/metric_chart?metric=bogus")
    assert response.status_code == 400


def _get_device_disabled_until(db_path: str, device_id: int) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT disabled_until FROM devices WHERE device_id=?", (device_id,)
        ).fetchone()
        return int(row["disabled_until"]) if row and row["disabled_until"] else 0
    finally:
        conn.close()


def test_set_device_disabled_until_sets_future_timestamp(flask_test_client):  # noqa: F811
    """POSTing a future absolute timestamp must persist to devices.disabled_until.

    The "Disable for" UI control sends epoch-seconds; this verifies the route
    correctly stores that timestamp so the next /status round-trips it. Guards
    against regressions that would silently drop or truncate the value.
    """
    test_db_path = os.environ.get("TEST_DB_NAME")
    assert test_db_path
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    device_id = conn.execute(
        "SELECT device_id FROM devices LIMIT 1"
    ).fetchone()["device_id"]
    conn.close()

    target = int(time.time()) + 1800
    response = flask_test_client.post(
        "/api/v1/set_device_disabled_until",
        json={"device_id": device_id, "disabled_until": target},
    )
    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert abs(response.json["disabled_until"] - target) <= 2
    stored = _get_device_disabled_until(test_db_path, device_id)
    assert abs(stored - target) <= 2


def test_set_device_disabled_until_past_reenables(flask_test_client):  # noqa: F811
    """A past-or-equal timestamp must clamp to 0 (re-enable rules for device).

    The UI clicks − until the remaining time would go negative; this path is
    the only way to re-enable rules on a device from that control. If clamp
    logic regressed (e.g. stored a past timestamp verbatim), the device would
    appear disabled forever from the server's perspective.
    """
    test_db_path = os.environ.get("TEST_DB_NAME")
    assert test_db_path
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    device_id = conn.execute(
        "SELECT device_id FROM devices LIMIT 1"
    ).fetchone()["device_id"]
    # Pre-seed a disable so we can verify it actually gets cleared
    conn.execute(
        "UPDATE devices SET disabled_until=? WHERE device_id=?",
        (int(time.time()) + 3600, device_id),
    )
    conn.commit()
    conn.close()

    response = flask_test_client.post(
        "/api/v1/set_device_disabled_until",
        json={"device_id": device_id, "disabled_until": int(time.time()) - 10},
    )
    assert response.status_code == 200
    assert response.json["disabled_until"] == 0
    assert _get_device_disabled_until(test_db_path, device_id) == 0


def test_set_device_disabled_until_rejects_invalid(flask_test_client):  # noqa: F811
    """Missing/non-int fields must 400, not silently write garbage to the DB."""
    response = flask_test_client.post(
        "/api/v1/set_device_disabled_until", json={"device_id": 1}
    )
    assert response.status_code == 400


def test_status_endpoint_with_schema_validation(flask_test_client):  # noqa: F811
    """Test that the status endpoint works with a database that has all required columns.

    This test ensures that the database schema matches what the code expects,
    preventing 'no such column' errors in production.
    """
    # First, verify the test database has the expected schema
    test_db_path = os.environ.get("TEST_DB_NAME")
    assert test_db_path, "TEST_DB_NAME environment variable should be set"

    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get the schema for the devices table
    cursor.execute("PRAGMA table_info(devices)")
    columns = [row["name"] for row in cursor.fetchall()]

    # Verify all expected columns exist
    expected_columns = [
        "device_id",
        "device_name",
        "ae200_device_id",
        "disabled_until",
        "notes",
    ]
    for expected_col in expected_columns:
        assert expected_col in columns, (
            f"Missing required column '{expected_col}' in devices table. Found columns: {columns}"
        )

    # Add a test device with all columns to ensure the query works
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO devices (device_name, ae200_device_id, disabled_until, notes)
        VALUES (?, ?, ?, ?)
    """,
        ("Test Device", 1, None, "Test notes"),
    )

    # Add a status entry
    cursor.execute(
        """
        INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
        VALUES (?, ?, ?, ?, ?)
    """,
        (
            cursor.lastrowid,
            int(time.time()),
            60,
            240,
            '{"Drive": "ON", "FanSpeed": "LOW"}',
        ),
    )
    conn.commit()
    conn.close()

    # Now test the endpoint - this should work without schema errors
    response = flask_test_client.get("/api/v1/status")
    assert response.status_code == 200
    response_json = response.json
    assert "devices" in response_json
    assert len(response_json["devices"]) >= 1

    # Verify the device data includes all expected fields
    test_device = next(
        (d for d in response_json["devices"] if d["device_name"] == "Test Device"), None
    )
    assert test_device is not None, "Test device should be returned"
    assert "notes" in test_device, "Device should include notes field"
    assert test_device["notes"] == "Test notes"


@skip_on_github
@patch("app.weather.get_weather_data")
@patch("app.airquality.get_aqi")
def test_weather_endpoint(
    mock_get_airquality, mock_get_weather_data, flask_test_client
):  # noqa: F811
    # Use new mock helper
    MockHelper.setup_weather_mocks(mock_get_airquality, mock_get_weather_data, 45, 72)

    # If this status endpoint also uses db.get_db_connection,
    # it will now correctly use the overridden test DB.
    response = flask_test_client.get("/api/v1/weather")
    assert response.status_code == 200
    response_json = response.json
    logging.info(" /weather: %s", response_json)
    assert "aqi" in response_json
    assert "weather" in response_json


# pylint: disable=too-many-arguments, disable=too-many-positional-arguments
BROADWAY_SOUTH = 10


@pytest.mark.parametrize(
    "start_speed,target_speed,expected_calls",
    [
        (1, 1, 0),  # Same speed - should not call set_fan_speed
        (1, 2, 1),  # Different speed - should call set_fan_speed once
        (1, 3, 1),  # Different speed - should call set_fan_speed once
        (1, 4, 1),  # Different speed - should call set_fan_speed once
        (2, 1, 1),  # Different speed - should call set_fan_speed once
        (2, 2, 0),  # Same speed - should not call set_fan_speed
        (2, 3, 1),  # Different speed - should call set_fan_speed once
        (2, 4, 1),  # Different speed - should call set_fan_speed once
    ],
)
def test_set_fan_speed_endpoint(
    flask_test_client, start_speed, target_speed, expected_calls
):  # noqa: F811
    # Set up simulator with initial speed
    ae200.set_fan_speed(BROADWAY_SOUTH, start_speed)
    now = int(time.time())  #

    # get device_id
    conn = sqlite3.connect(os.environ["TEST_DB_NAME"])
    conn.row_factory = sqlite3.Row
    device_id = db.get_or_create_device_id(conn, "Broadway Test")
    c = conn.cursor()
    c.execute(
        "UPDATE devices set ae200_device_id=? where device_id=?",
        (BROADWAY_SOUTH, device_id),
    )
    conn.commit()
    conn.close()

    # Send the /set_fan_speed
    response = flask_test_client.post(
        "/api/v1/set_fan_speed",
        json={"device_id": device_id, "fan_speed": target_speed},
    )
    assert response.status_code == 200  # Check for successful HTTP status
    response_json = response.json
    assert response_json["status"] == "ok"
    assert response_json["device_id"] == device_id
    assert str(response_json["unit"]) == str(BROADWAY_SOUTH)
    assert response_json["speed"] == target_speed

    # Verify the simulator state was updated correctly
    device_info = ae200.get_device_info(BROADWAY_SOUTH)
    speed_names = DeviceTestData.get_speed_names()
    expected_speed_name = speed_names[target_speed]
    assert device_info["FanSpeed"] == expected_speed_name

    # Verify that the database got updated only when speed changes
    if expected_calls > 0:
        # Note that we are using the TEST_DB_NAME put in the environment.
        test_conn_verify = sqlite3.connect(os.environ["TEST_DB_NAME"])
        test_conn_verify.row_factory = sqlite3.Row
        cursor = test_conn_verify.cursor()

        cursor.execute("SELECT * from devices where device_name=?", ("Broadway Test",))
        devrow = cursor.fetchone()
        logging.debug("row=%s", dict(devrow))
        assert (
            devrow["disabled_until"] >= now + 60
        )  # make sure that rules are disabled for at least 60 seconds...
        device_id = devrow["device_id"]
        cursor.execute(
            "SELECT * from devlog where device_id=? order by logtime desc", (device_id,)
        )
        devlogrow = cursor.fetchone()
        extracted_status = ae200.extract_drive_and_fan_speed(
            json.loads(devlogrow["status_json"])
        )
        assert extracted_status["fan_speed"] == target_speed

        cursor.execute(
            "SELECT ipaddr, device_id, new_value, agent FROM changelog order by changelog_id DESC limit 2"
        )
        changelog_entries = cursor.fetchall()

        assert len(changelog_entries) == 2  # should have two entries
        for cl in changelog_entries:
            logging.debug("changelog_entry=%s", dict(cl))
            assert cl["ipaddr"] == "127.0.0.1"  # Flask test client IP
            assert cl["device_id"] == device_id
            assert cl["agent"].startswith("Werkzeug") or cl["agent"] == "web"

        test_conn_verify.close()


def _link_device_to_unit(conn, name):
    """Create a device linked to the BROADWAY_SOUTH simulator unit; return its id."""
    device_id = db.get_or_create_device_id(conn, name)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE devices SET ae200_device_id=? WHERE device_id=?",
        (BROADWAY_SOUTH, device_id),
    )
    conn.commit()
    return device_id


def _latest_devlog_status(conn, device_id):
    """Return the extracted drive/fan_speed of the most recent devlog row."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status_json FROM devlog WHERE device_id=? ORDER BY logtime DESC",
        (device_id,),
    )
    row = cursor.fetchone()
    return ae200.extract_drive_and_fan_speed(json.loads(row["status_json"]))


def test_set_body_drive_records_commanded_drive_when_readback_is_stale(
    test_database_conn,
):  # noqa: F811
    """Regression: set_body_drive must record the commanded Drive even when the
    hardware read-back still reports the old state (the read-back can race the
    command). Otherwise /status reports the stale drive and the UI snaps back to
    the prior selection."""
    conn = test_database_conn
    device_id = _link_device_to_unit(conn, "Readback Race Drive Test")

    # Unit is currently ON; the post-command read-back returns a STALE status
    # that still shows Drive=ON even though we are commanding OFF.
    stale_status = {"Drive": "ON", "FanSpeed": "AUTO", "InletTemp": "22.0"}
    with patch.object(ae200, "get_device_drive", return_value=1), patch.object(
        ae200, "set_drive"
    ) as mock_set_drive, patch.object(
        ae200, "get_device_info", return_value=dict(stale_status)
    ):
        rules_engine.set_body_drive(
            conn,
            db.DriveControl(device_id=device_id, drive=0),
            "127.0.0.1",
            "web",
        )
        mock_set_drive.assert_called_once()

    # The recorded status must reflect the commanded OFF, not the stale ON.
    assert _latest_devlog_status(conn, device_id)["drive"] == 0


def test_set_body_fan_speed_records_commanded_speed_when_readback_is_stale(
    test_database_conn,
):  # noqa: F811
    """Regression: set_body_fan_speed must record the commanded FanSpeed even
    when the hardware read-back still reports the old speed."""
    conn = test_database_conn
    device_id = _link_device_to_unit(conn, "Readback Race Speed Test")

    # Unit is currently on LOW (1); the read-back still reports LOW even though
    # we are commanding MID1 (3).
    stale_status = {"Drive": "ON", "FanSpeed": "LOW", "InletTemp": "22.0"}
    with patch.object(ae200, "get_device_fan_speed", return_value=1), patch.object(
        ae200, "set_fan_speed"
    ) as mock_set_speed, patch.object(
        ae200, "get_device_info", return_value=dict(stale_status)
    ):
        rules_engine.set_body_fan_speed(
            conn,
            db.SpeedControl(device_id=device_id, fan_speed=3),
            "127.0.0.1",
            "web",
        )
        mock_set_speed.assert_called_once()

    assert _latest_devlog_status(conn, device_id)["fan_speed"] == 3


@pytest.mark.parametrize(
    "start_set_temp,target_set_temp,expected_changelog_delta",
    [
        (21.0, 21.0, 0),  # Same temperature - should not create changelog entry
        (21.0, 22.0, 1),  # Different temperature - should create one changelog entry
    ],
)
def test_set_temp_endpoint(
    flask_test_client, start_set_temp, target_set_temp, expected_changelog_delta
):  # noqa: F811
    # Link a dedicated device to the AE-200 simulator unit
    ae200_unit_id = BROADWAY_SOUTH

    conn = sqlite3.connect(os.environ["TEST_DB_NAME"])
    conn.row_factory = sqlite3.Row
    device_id = db.get_or_create_device_id(conn, "Broadway SetTemp Test")

    cursor = conn.cursor()
    cursor.execute(
        "UPDATE devices SET ae200_device_id=? WHERE device_id=?",
        (ae200_unit_id, device_id),
    )
    conn.commit()

    # Initialize simulator with a starting set temperature
    ae200.set_set_temp(ae200_unit_id, start_set_temp)

    # Capture changelog and devlog counts before the call
    cursor.execute(
        "SELECT COUNT(*) AS n FROM changelog WHERE device_id=?", (device_id,)
    )
    before_changelog = cursor.fetchone()["n"]

    cursor.execute(
        "SELECT COUNT(*) AS n FROM devlog WHERE device_id=?", (device_id,)
    )
    before_devlog = cursor.fetchone()["n"]
    conn.close()

    # Call the /set_temp endpoint
    response = flask_test_client.post(
        "/api/v1/set_temp",
        json={"device_id": device_id, "set_temp_c": target_set_temp},
    )
    assert response.status_code == 200
    response_json = response.json
    assert response_json["status"] == "ok"
    assert response_json["device_id"] == device_id
    assert str(response_json["unit"]) == str(ae200_unit_id)
    assert response_json["set_temp_c"] == pytest.approx(target_set_temp)

    # Verify simulator state reflects the canonical set temperature
    device_info = ae200.get_device_info(ae200_unit_id)
    current_set_temp_raw = device_info.get("SetTemp")
    # Simulator stores SetTemp as a string; convert to float for comparison
    if current_set_temp_raw is not None and current_set_temp_raw != "":
        current_set_temp = float(current_set_temp_raw)
        # After the endpoint, the simulator should report the latest requested temperature
        assert current_set_temp == pytest.approx(target_set_temp)

    # Re-open connection to check database effects
    verify_conn = sqlite3.connect(os.environ["TEST_DB_NAME"])
    verify_conn.row_factory = sqlite3.Row
    verify_cursor = verify_conn.cursor()

    verify_cursor.execute(
        "SELECT COUNT(*) AS n FROM devlog WHERE device_id=?", (device_id,)
    )
    after_devlog = verify_cursor.fetchone()["n"]
    assert after_devlog == before_devlog + 1

    verify_cursor.execute(
        "SELECT COUNT(*) AS n FROM changelog WHERE device_id=?", (device_id,)
    )
    after_changelog = verify_cursor.fetchone()["n"]
    assert after_changelog == before_changelog + expected_changelog_delta

    verify_conn.close()


def test_alerts_active_endpoint(flask_test_client):  # noqa: F811
    """Test the /api/v1/alerts/active endpoint"""
    response = flask_test_client.get("/api/v1/alerts/active")
    assert response.status_code == 200
    alerts = response.json
    assert isinstance(alerts, list)


def test_alerts_active_endpoint_with_details(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    """Test the /api/v1/alerts/active endpoint with include_details parameter"""

    conn = test_database_conn_with_test_data[0]
    device_id = test_database_conn_with_test_data[1]

    # Create an alert with corresponding status entry using helper
    now = int(time.time())
    alert_time = now - 300

    # Add alert to existing device
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
        (device_id, alert_time, 600, 250, '{"Mode": "AUTO", "Drive": "ON", "FanSpeed": "MEDIUM"}'),
    )
    cursor.execute(
        "INSERT INTO alerts (device_id, alert_type, alert_value, start_time, end_time) VALUES (?, ?, ?, ?, ?)",
        (device_id, "ErrorSign", "ON", alert_time, None),
    )
    conn.commit()

    # Request without details
    response = flask_test_client.get("/api/v1/alerts/active")
    assert response.status_code == 200
    alerts = response.json
    assert len(alerts) >= 1
    assert "details" not in alerts[0]

    # Request with details
    response = flask_test_client.get("/api/v1/alerts/active?include_details=true")
    assert response.status_code == 200
    alerts = response.json
    assert len(alerts) >= 1
    assert "details" in alerts[0]
    assert alerts[0]["details"]["mode"] == "AUTO"
    assert alerts[0]["details"]["fan_speed"] == "MEDIUM"


def test_alerts_history_endpoint(flask_test_client):  # noqa: F811
    """Test the /api/v1/alerts/history endpoint"""
    response = flask_test_client.get("/api/v1/alerts/history")
    assert response.status_code == 200
    alerts = response.json
    assert isinstance(alerts, list)


def test_alerts_history_endpoint_with_details(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    """Test the /api/v1/alerts/history endpoint with include_details parameter"""

    conn = test_database_conn_with_test_data[0]
    device_id = test_database_conn_with_test_data[1]

    # Create a resolved alert with corresponding status entry
    now = int(time.time())
    alert_start = now - 1000

    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
        (device_id, alert_start, 600, 250, '{"Mode": "AUTO", "Drive": "ON", "FanSpeed": "HIGH"}'),
    )
    cursor.execute(
        "INSERT INTO alerts (device_id, alert_type, alert_value, start_time, end_time) VALUES (?, ?, ?, ?, ?)",
        (device_id, "ErrorSign", "ON", alert_start, now - 500),
    )
    conn.commit()

    # Request without details
    response = flask_test_client.get("/api/v1/alerts/history")
    assert response.status_code == 200
    alerts = response.json
    assert len(alerts) >= 1
    assert "details" not in alerts[0]

    # Request with details
    response = flask_test_client.get("/api/v1/alerts/history?include_details=true")
    assert response.status_code == 200
    alerts = response.json
    assert len(alerts) >= 1
    assert "details" in alerts[0]
    assert alerts[0]["details"]["mode"] == "AUTO"
    assert alerts[0]["details"]["fan_speed"] == "HIGH"


def test_alerts_history_endpoint_limit(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    """Test the /api/v1/alerts/history endpoint with limit parameter"""

    conn = test_database_conn_with_test_data[0]
    device_id = test_database_conn_with_test_data[1]

    # Create multiple alerts
    now = int(time.time())
    cursor = conn.cursor()

    for i in range(5):
        cursor.execute(
            "INSERT INTO alerts (device_id, alert_type, alert_value, start_time, end_time) VALUES (?, ?, ?, ?, ?)",
            (
                device_id,
                "ErrorSign",
                "ON",
                now - 5000 + i * 100,
                now - 5000 + i * 100 + 50,
            ),
        )

    conn.commit()

    # Request with limit
    response = flask_test_client.get("/api/v1/alerts/history?limit=3")
    assert response.status_code == 200
    alerts = response.json
    assert len(alerts) == 3


def test_update_note_endpoint(flask_test_client, test_database_conn_with_test_data):  # noqa: F811
    """Test the /api/v1/update_note endpoint"""
    conn = test_database_conn_with_test_data[0]
    device_id = test_database_conn_with_test_data[1]

    # Update note
    response = flask_test_client.post(
        "/api/v1/update_note",
        json={"device_id": device_id, "notes": "Test note"},
    )
    assert response.status_code == 200
    response_json = response.json
    assert response_json["status"] == "ok"
    assert response_json["device_id"] == device_id

    # Verify note was saved
    cursor = conn.cursor()
    cursor.execute("SELECT notes FROM devices WHERE device_id = ?", (device_id,))
    row = cursor.fetchone()
    assert row["notes"] == "Test note"

    # Clear note
    response = flask_test_client.post(
        "/api/v1/update_note",
        json={"device_id": device_id, "notes": None},
    )
    assert response.status_code == 200

    # Verify note was cleared
    cursor.execute("SELECT notes FROM devices WHERE device_id = ?", (device_id,))
    row = cursor.fetchone()
    assert row["notes"] is None


def test_debug_db_devices_endpoint(flask_test_client, test_database_conn_with_test_data):  # noqa: F811
    """Test the /api/v1/debug/db_devices endpoint"""
    conn = test_database_conn_with_test_data[0]
    device_id = test_database_conn_with_test_data[1]

    # Add a device name
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE devices SET device_name = ? WHERE device_id = ?",
        ("Test Device Name", device_id),
    )
    conn.commit()

    response = flask_test_client.get("/api/v1/debug/db_devices")
    assert response.status_code == 200
    response_json = response.json
    assert "names" in response_json
    assert "data" in response_json
    assert isinstance(response_json["names"], list)
    assert isinstance(response_json["data"], list)
    assert len(response_json["names"]) > 0
    assert len(response_json["data"]) > 0


@patch("app.routes_api.hubitat.get_all_devices")
def test_debug_db_devices_enriches_names_with_hubitat_label(
    mock_get_all_devices, flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    """Database device names list shows 'name (label)' when Hubitat has a matching device."""
    conn = test_database_conn_with_test_data[0]
    device_id = test_database_conn_with_test_data[1]
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE devices SET device_name = ? WHERE device_id = ?",
        ("Test Device Name", device_id),
    )
    conn.commit()

    mock_get_all_devices.return_value = [
        {"name": "Test Device Name", "label": "Short Label", "id": "x", "capabilities": []}
    ]
    response = flask_test_client.get("/api/v1/debug/db_devices")
    assert response.status_code == 200
    names = response.json["names"]
    assert "Test Device Name (Short Label)" in names


@patch("app.routes_api.hubitat.get_all_devices")
def test_debug_hubitat_devices_endpoint(mock_get_all_devices, flask_test_client):  # noqa: F811
    """Test the /api/v1/debug/hubitat_devices endpoint"""
    # Mock Hubitat devices
    mock_get_all_devices.return_value = [
        {"name": "Test Hubitat Device", "id": 1, "capabilities": ["TemperatureMeasurement"]}
    ]

    response = flask_test_client.get("/api/v1/debug/hubitat_devices")
    assert response.status_code == 200
    response_json = response.json
    assert "names" in response_json
    assert "data" in response_json
    assert isinstance(response_json["names"], list)
    assert isinstance(response_json["data"], list)
    assert "Test Hubitat Device" in response_json["names"]


@patch("app.routes_api.hubitat.get_all_devices")
def test_debug_hubitat_devices_shows_name_and_label_when_label_present(
    mock_get_all_devices, flask_test_client
):  # noqa: F811
    """Hubitat device names list shows 'name (label)' when device has a label."""
    mock_get_all_devices.return_value = [
        {
            "name": "Lobby Sensor on Somerville Broadway",
            "label": "Lobby Sensor",
            "id": "abc",
            "capabilities": ["TemperatureMeasurement"],
        }
    ]
    response = flask_test_client.get("/api/v1/debug/hubitat_devices")
    assert response.status_code == 200
    names = response.json["names"]
    assert "Lobby Sensor on Somerville Broadway (Lobby Sensor)" in names


@patch("app.routes_api.hubitat.get_all_devices")
def test_temperature_api_series_uses_hubitat_label_when_available(
    mock_get_all_devices, flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    """Temperature series API uses Hubitat label as display name when Hubitat has a match."""
    device_id = test_database_conn_with_test_data[1]
    mock_get_all_devices.return_value = [
        {
            "name": "Broadway Test",
            "label": "Broadway",
            "id": "y",
            "capabilities": ["TemperatureMeasurement"],
        }
    ]
    response = flask_test_client.get("/api/v1/temperature?device_id=" + str(device_id))
    assert response.status_code == 200
    series = response.json.get("series", [])
    assert series, "expected at least one series"
    series_names = [s["name"] for s in series]
    assert "Broadway" in series_names
    assert "device_id" in series[0], "series must include device_id for chart keying"


def test_lighting_api_basic_series_shape(flask_test_client):  # noqa: F811
    """Lighting series API returns series list with expected structure and numeric data."""
    response = flask_test_client.get("/api/v1/lighting")
    assert response.status_code == 200
    data = response.json
    assert "series" in data
    assert isinstance(data["series"], list)
    if data["series"]:
        first = data["series"][0]
        assert "name" in first
        assert "data" in first
        assert isinstance(first["data"], list)
        # Each datapoint should be [timestamp, value] with numeric value
        if first["data"]:
            ts, val = first["data"][0]
            assert isinstance(ts, int)
            assert isinstance(val, (int, float))


@patch("app.routes_api.hubitat.get_all_devices")
def test_debug_hubitat_devices_endpoint_error(mock_get_all_devices, flask_test_client):  # noqa: F811
    """Test the /api/v1/debug/hubitat_devices endpoint handles errors"""
    # Mock error - use RuntimeError which is caught by the handler
    mock_get_all_devices.side_effect = RuntimeError("Hubitat connection error")

    response = flask_test_client.get("/api/v1/debug/hubitat_devices")
    assert response.status_code == 500
    response_json = response.json
    assert "error" in response_json


@patch("app.routes_api.ae200.runner.run_async_safely")
@patch("app.routes_api.ae200.get_devices")
def test_debug_ae200_devices_endpoint(
    mock_get_devices, mock_run_async, flask_test_client
):  # noqa: F811
    """Test the /api/v1/debug/ae200_devices endpoint"""
    # Mock AE-200 devices
    mock_get_devices.return_value = [
        {"name": "Test AE200 Device", "id": "10"}
    ]
    # Mock the async runner: close the coroutine to avoid "coroutine was never awaited"
    def _mock_run_async(coro):
        coro.close()
        return {"10": {"Drive": "ON", "FanSpeed": "LOW"}}
    mock_run_async.side_effect = _mock_run_async

    response = flask_test_client.get("/api/v1/debug/ae200_devices")
    assert response.status_code == 200
    response_json = response.json
    assert "names" in response_json
    assert "devices" in response_json
    assert "details" in response_json
    assert isinstance(response_json["names"], list)
    assert isinstance(response_json["devices"], list)
    assert isinstance(response_json["details"], dict)
    assert "Test AE200 Device" in response_json["names"]


@patch("app.routes_api.ae200.get_devices")
def test_debug_ae200_devices_endpoint_error(mock_get_devices, flask_test_client):  # noqa: F811
    """Test the /api/v1/debug/ae200_devices endpoint handles errors"""
    # Mock error - use RuntimeError which is caught by the handler
    mock_get_devices.side_effect = RuntimeError("AE200 connection error")

    response = flask_test_client.get("/api/v1/debug/ae200_devices")
    assert response.status_code == 500
    response_json = response.json
    assert "error" in response_json


def test_disable_rules_api_enable_and_disable(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    """disable-rules API enables (seconds=0) and disables (seconds=N) rules; DB state matches (replaces Playwright rules test)."""
    conn = test_database_conn_with_test_data[0]
    client = flask_test_client

    # Enable rules
    r = client.get("/api/v1/disable-rules?seconds=0")
    assert r.status_code == 200
    assert rules_engine.all_rules_disabled_until(conn) == 0

    # Disable for 1 hour
    r = client.get("/api/v1/disable-rules?seconds=3600")
    assert r.status_code == 200
    disabled_until = rules_engine.all_rules_disabled_until(conn)
    assert disabled_until != 0
    min_expected = int(time.time()) + 50 * 60  # at least ~50 minutes from now
    assert disabled_until >= min_expected, (
        f"rules should be disabled until at least {min_expected}, got {disabled_until}"
    )


def test_rules_master_api_default_and_toggle(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    """rules_master API reports default enabled, and toggling persists to the database."""
    conn = test_database_conn_with_test_data[0]
    client = flask_test_client

    # By default, master should be enabled
    r = client.get("/api/v1/rules_master")
    assert r.status_code == 200
    assert r.json == {"enabled": True}
    assert db.get_rules_master_enabled(conn) is True

    # Turn master OFF
    r = client.post("/api/v1/rules_master", json={"enabled": False})
    assert r.status_code == 200
    assert r.json == {"enabled": False}
    assert db.get_rules_master_enabled(conn) is False

    # Verify underlying RULES_MASTER device row has a future disabled_until
    cursor = conn.cursor()
    cursor.execute(
        "SELECT disabled_until FROM devices WHERE device_name = ?", ("rules_master",)
    )
    row = cursor.fetchone()
    assert row is not None
    disabled_until = row["disabled_until"]
    assert disabled_until is not None and disabled_until > int(time.time())

    # Turn master back ON
    r = client.post("/api/v1/rules_master", json={"enabled": True})
    assert r.status_code == 200
    assert r.json == {"enabled": True}
    assert db.get_rules_master_enabled(conn) is True

    cursor.execute(
        "SELECT disabled_until FROM devices WHERE device_name = ?", ("rules_master",)
    )
    row = cursor.fetchone()
    assert row is not None
    assert row["disabled_until"] == 0
