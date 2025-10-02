"""
test Flask endpoints
"""
import logging
import sqlite3
import os
import json
import time
import tempfile
from unittest.mock import patch

import pytest
from conftest import client_with_db, skip_on_github  # noqa: F401  # pylint: disable=unused-import
from helpers.data_factories import DeviceTestData
from helpers.mock_helpers import MockHelper

from app import ae200
from app import db
from app.constants import __version__
from app.services.device_service import DeviceService

logger = logging.getLogger(__name__)

# Disable websockets debug
@pytest.fixture(autouse=True)
def reduce_websockets_logging():
    logging.getLogger("websockets.client_with_db").setLevel(logging.INFO)


def test_get_version(client_with_db):   # noqa: F811

    response = client_with_db.get("/version")
    assert response.status_code == 200
    assert response.data.decode('utf-8') == f'version: {__version__}'

    response = client_with_db.get("/api/v1/version")
    assert response.status_code == 200
    assert response.json == {'version': __version__}


def test_status_endpoint(client_with_db):  # noqa: F811
    response = client_with_db.get("/api/v1/status")
    assert response.status_code == 200
    response_json = response.json
    logging.info(" /status: %s", response_json)
    assert "devices" in response_json


def test_status_endpoint_with_schema_validation(client_with_db):  # noqa: F811
    """Test that the status endpoint works with a database that has all required columns.

    This test ensures that the database schema matches what the code expects,
    preventing 'no such column' errors in production.
    """
    # First, verify the test database has the expected schema
    test_db_path = os.environ.get('TEST_DB_PATH')
    assert test_db_path, "TEST_DB_PATH environment variable should be set"

    with sqlite3.connect(test_db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get the schema for the devices table
        cursor.execute("PRAGMA table_info(devices)")
        columns = [row['name'] for row in cursor.fetchall()]

        # Verify all expected columns exist
        expected_columns = ['device_id', 'device_name', 'ae200_device_id', 'disabled_until', 'notes']
        for expected_col in expected_columns:
            assert expected_col in columns, f"Missing required column '{expected_col}' in devices table. Found columns: {columns}"

    # Add a test device with all columns to ensure the query works
    with sqlite3.connect(test_db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO devices (device_name, ae200_device_id, disabled_until, notes)
            VALUES (?, ?, ?, ?)
        """, ("Test Device", 1, None, "Test notes"))

        # Add a status entry
        cursor.execute("""
            INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
            VALUES (?, ?, ?, ?, ?)
        """, (cursor.lastrowid, int(time.time()), 60, 240, '{"Drive": "ON", "FanSpeed": "LOW"}'))
        conn.commit()

    # Now test the endpoint - this should work without schema errors
    response = client_with_db.get("/api/v1/status")
    assert response.status_code == 200
    response_json = response.json
    assert "devices" in response_json
    assert len(response_json["devices"]) >= 1

    # Verify the device data includes all expected fields
    test_device = next((d for d in response_json["devices"] if d["device_name"] == "Test Device"), None)
    assert test_device is not None, "Test device should be returned"
    assert "notes" in test_device, "Device should include notes field"
    assert test_device["notes"] == "Test notes"


def test_status_endpoint_schema_mismatch_detection():
    """Test that detects when the database schema doesn't match code expectations.

    This test simulates the production issue where the database was created
    with an older schema missing the 'notes' column.
    """

    # Create a temporary database with the old schema (missing notes column)
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
        db_path = tf.name

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Create devices table WITHOUT the notes column (simulating old schema)
            cursor.execute("""
                CREATE TABLE devices (
                    device_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_name TEXT UNIQUE NOT NULL,
                    ae200_device_id INTEGER,
                    disabled_until INTEGER
                )
            """)

            # Create devlog table
            cursor.execute("""
                CREATE TABLE devlog (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    logtime INTEGER NOT NULL,
                    duration INTEGER NOT NULL DEFAULT 1,
                    temp10x INTEGER,
                    status_json TEXT,
                    FOREIGN KEY (device_id) REFERENCES devices (device_id)
                )
            """)

            # Add test data
            cursor.execute("INSERT INTO devices (device_name, ae200_device_id) VALUES (?, ?)", ("Test Device", 1))
            device_id = cursor.lastrowid
            cursor.execute("""
                INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
                VALUES (?, ?, ?, ?, ?)
            """, (device_id, int(time.time()), 60, 240, '{"Drive": "ON", "FanSpeed": "LOW"}'))
            conn.commit()

        # Set up environment to use this database
        original_db_path = os.environ.get('DB_PATH')
        original_test_db_name = os.environ.get('TEST_DB_PATH')

        try:
            os.environ['DB_PATH'] = db_path
            os.environ['TEST_DB_PATH'] = db_path

            # This should fail with the same error we saw in production
            device_service = DeviceService()

            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row

                # This should raise sqlite3.OperationalError: no such column: b.notes
                with pytest.raises(sqlite3.OperationalError, match="no such column: b.notes"):
                    device_service.get_device_status(conn)

        finally:
            # Restore environment
            if original_db_path is not None:
                os.environ['DB_PATH'] = original_db_path
            elif 'DB_PATH' in os.environ:
                del os.environ['DB_PATH']

            if original_test_db_name is not None:
                os.environ['TEST_DB_PATH'] = original_test_db_name
            elif 'TEST_DB_PATH' in os.environ:
                del os.environ['TEST_DB_PATH']

    finally:
        # Clean up temporary file
        os.unlink(db_path)


@skip_on_github
@patch("app.weather.get_weather_data")
@patch("app.airquality.get_aqi")
def test_weather_endpoint(mock_get_airquality, mock_get_weather_data, client_with_db):  # noqa: F811
    # Use new mock helper
    MockHelper.setup_weather_mocks(mock_get_airquality, mock_get_weather_data, 45, 72)

    # If this status endpoint also uses db.get_db_connection,
    # it will now correctly use the overridden test DB.
    response = client_with_db.get("/api/v1/weather")
    assert response.status_code == 200
    response_json = response.json
    logging.info(" /weather: %s", response_json)
    assert "aqi" in response_json
    assert "weather" in response_json


# pylint: disable=too-many-arguments, disable=too-many-positional-arguments
BROADWAY_SOUTH=10
@pytest.mark.parametrize("start_speed,target_speed,expected_calls", [
    (1, 1, 0),  # Same speed - should not call set_fan_speed
    (1, 2, 1),  # Different speed - should call set_fan_speed once
    (1, 3, 1),  # Different speed - should call set_fan_speed once
    (1, 4, 1),  # Different speed - should call set_fan_speed once
    (2, 1, 1),  # Different speed - should call set_fan_speed once
    (2, 2, 0),  # Same speed - should not call set_fan_speed
    (2, 3, 1),  # Different speed - should call set_fan_speed once
    (2, 4, 1),  # Different speed - should call set_fan_speed once
])
def test_set_fan_speed_endpoint(client_with_db, start_speed, target_speed, expected_calls): # noqa: F811
    # Set up simulator with initial speed
    ae200.set_fan_speed(BROADWAY_SOUTH, start_speed)

    # get device_id
    with sqlite3.connect(os.environ['TEST_DB_PATH']) as test_conn:
        test_conn.row_factory = sqlite3.Row
        device_id = db.get_or_create_device_id(test_conn, "Broadway South")
        c = test_conn.cursor()
        c.execute("UPDATE devices set ae200_device_id=? where device_id=?",(BROADWAY_SOUTH,device_id))
        test_conn.commit()

    # Send the /set_fan_speed
    response = client_with_db.post(
        "/api/v1/set_fan_speed",
        json={"device_id": device_id, "fan_speed": target_speed}
    )
    assert response.status_code == 200  # Check for successful HTTP status
    response_json = response.json
    assert response_json["status"] == "ok"
    assert response_json["device_id"] == device_id
    assert str(response_json['unit']) == str(BROADWAY_SOUTH)
    assert response_json["speed"] == target_speed

    # Verify the simulator state was updated correctly
    device_info = ae200.get_device_info(BROADWAY_SOUTH)
    speed_names = DeviceTestData.get_speed_names()
    expected_speed_name = speed_names[target_speed]
    assert device_info['FanSpeed'] == expected_speed_name

    # Verify that the database got updated only when speed changes
    if expected_calls > 0:
        # Note that we are using the TEST_DB_PATH put in the environment.
        with sqlite3.connect(os.environ['TEST_DB_PATH']) as test_conn_verify:
            test_conn_verify.row_factory = sqlite3.Row
            cursor = test_conn_verify.cursor()
            cursor.execute("SELECT ipaddr, device_id, new_value, agent FROM changelog order by changelog_id DESC limit 1")
            changelog_entry = cursor.fetchone()
            assert changelog_entry is not None
            logging.debug("changelog_entry=%s",dict(changelog_entry))
            assert changelog_entry['ipaddr'] == '127.0.0.1'  # Flask test client IP
            assert changelog_entry['device_id'] == device_id
            assert changelog_entry['new_value'] == str(target_speed)
            assert changelog_entry['agent'] == 'web'

            cursor.execute("SELECT * from devices where device_name=?", ("Broadway South",))
            row = cursor.fetchone()
            logging.debug("row=%s", dict(row))
            device_id = row['device_id']
            cursor.execute("SELECT * from devlog where device_id=? order by logtime desc", (device_id,))
            row = cursor.fetchone()
            extracted_status = ae200.extract_drive_and_fan_speed(json.loads(row['status_json']))
            assert extracted_status['fan_speed'] == target_speed
