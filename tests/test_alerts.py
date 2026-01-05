"""
Tests for alert functionality including device status details
"""

import json
import time
import logging

from helpers.data_factories import AlertTestData

from app import db

logger = logging.getLogger(__name__)


def test_format_alert_type_display():
    """Test formatting alert types to user-friendly display names"""
    assert db.format_alert_type_display("ErrorSign") == "Error"
    assert db.format_alert_type_display("FilterSign") == "Filter warning"
    assert db.format_alert_type_display("CheckWater") == "Water issue"

    # Test unknown types are returned as-is
    assert db.format_alert_type_display("UnknownType") == "UnknownType"


def test_extract_relevant_status_fields_valid():
    """Test extracting status fields from valid JSON"""
    status_json = json.dumps(
        {
            "Mode": "AUTO",
            "Drive": "ON",
            "InletTemp": "24.5",
            "FanSpeed": "MEDIUM",
            "ErrorSign": "ON",
        }
    )

    result = db.extract_relevant_status_fields(status_json)

    assert result is not None
    assert result["mode"] == "AUTO"
    assert result["drive"] == "ON"
    assert result["inlet_temp"] == "24.5"
    assert result["fan_speed"] == "MEDIUM"
    assert result["error_sign"] == "ON"


def test_extract_relevant_status_fields_invalid():
    """Test extracting status fields from invalid/None input"""
    assert db.extract_relevant_status_fields(None) is None
    assert db.extract_relevant_status_fields("") is None
    assert db.extract_relevant_status_fields("{invalid json") is None


def test_get_alert_device_status_rle_encoding(test_database_conn):
    """Test retrieving device status when alert time falls within RLE duration"""
    conn = test_database_conn

    cursor = conn.cursor()
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Test Device",))
    device_id = cursor.lastrowid

    # Insert a status entry at time 1000 that lasts 100 seconds (until 1100)
    status_json = json.dumps({"Mode": "AUTO", "Drive": "ON", "FanSpeed": "HIGH"})
    cursor.execute(
        "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
        (device_id, 1000, 100, 250, status_json),
    )

    conn.commit()

    # Alert at time 1050 (within the 1000-1100 range)
    result = db.get_alert_device_status(conn, device_id, 1050)

    assert result is not None
    assert result == (status_json, 1000)


def test_get_alert_device_status_not_found(test_database_conn):
    """Test retrieving device status when no record exists"""
    conn = test_database_conn

    cursor = conn.cursor()
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Test Device",))
    device_id = cursor.lastrowid

    conn.commit()

    result = db.get_alert_device_status(conn, device_id, 1000)
    assert result == (None, None)


def test_get_active_alerts_with_details(test_database_conn):
    """Test getting active alerts with device status details"""
    conn = test_database_conn

    now = int(time.time())
    alert_time = now - 300

    # Create device with alert using helper
    AlertTestData.create_device_with_alert(
        conn,
        "Device 1",
        "ErrorSign",
        {"Mode": "AUTO", "Drive": "ON", "FanSpeed": "MEDIUM", "InletTemp": "23.5"},
        alert_time,
        alert_value="ON",
        end_time=None
    )

    # Request without details
    alerts = db.get_active_alerts(conn, include_details=False)
    assert len(alerts) == 1
    assert "details" not in alerts[0]

    # Request with details
    alerts = db.get_active_alerts(conn, include_details=True)
    assert len(alerts) == 1
    assert "details" in alerts[0]
    assert alerts[0]["details"]["mode"] == "AUTO"
    assert alerts[0]["details"]["fan_speed"] == "MEDIUM"


def test_get_alert_history_with_details(test_database_conn):
    """Test getting alert history with device status details"""
    conn = test_database_conn

    now = int(time.time())
    alert_start = now - 1000

    # Create device with resolved alert using helper
    AlertTestData.create_device_with_alert(
        conn,
        "Device 1",
        "ErrorSign",
        {"Mode": "AUTO", "Drive": "ON", "FanSpeed": "HIGH"},
        alert_start,
        alert_value="ON",
        end_time=now - 500
    )

    # Request with details
    alerts = db.get_alert_history(conn, include_details=True)
    assert len(alerts) == 1
    assert "details" in alerts[0]
    assert alerts[0]["details"]["mode"] == "AUTO"
    assert alerts[0]["details"]["fan_speed"] == "HIGH"


def test_insert_or_update_alert_create_and_close(test_database_conn):
    """Test creating a new alert and then closing it"""
    conn = test_database_conn

    cursor = conn.cursor()
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Test Device",))
    device_id = cursor.lastrowid

    now = int(time.time())

    # Create alert
    db.insert_or_update_alert(conn, device_id, "ErrorSign", "ON", now)

    # Verify alert was created
    cursor.execute("SELECT * FROM alerts WHERE device_id=?", (device_id,))
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]["alert_value"] == "ON"
    assert rows[0]["end_time"] is None

    # Close it with OFF value
    end_time = now + 100
    db.insert_or_update_alert(conn, device_id, "ErrorSign", "OFF", end_time)

    # Verify alert was closed
    cursor.execute("SELECT * FROM alerts WHERE device_id=?", (device_id,))
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]["end_time"] == end_time
    assert rows[0]["alert_value"] == "ON"  # Original value preserved


def test_insert_or_update_alert_no_duplicate(test_database_conn):
    """Test that no duplicate alert is created when value doesn't change"""
    conn = test_database_conn

    cursor = conn.cursor()
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Test Device",))
    device_id = cursor.lastrowid

    now = int(time.time())

    # Insert alert with same value twice
    db.insert_or_update_alert(conn, device_id, "ErrorSign", "ON", now)
    db.insert_or_update_alert(conn, device_id, "ErrorSign", "ON", now + 10)

    # Verify only one alert was created
    cursor.execute("SELECT * FROM alerts WHERE device_id=?", (device_id,))
    rows = cursor.fetchall()
    assert len(rows) == 1


def test_get_alerts_for_device(test_database_conn):
    """Test getting all alerts for a specific device"""
    conn = test_database_conn

    cursor = conn.cursor()

    # Create two devices
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Device 1",))
    device_id1 = cursor.lastrowid
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Device 2",))
    device_id2 = cursor.lastrowid

    now = int(time.time())

    # Create alerts for device 1
    cursor.execute(
        "INSERT INTO alerts (device_id, alert_type, alert_value, start_time, end_time) VALUES (?, ?, ?, ?, ?)",
        (device_id1, "ErrorSign", "ON", now - 1000, now - 500),
    )
    cursor.execute(
        "INSERT INTO alerts (device_id, alert_type, alert_value, start_time, end_time) VALUES (?, ?, ?, ?, ?)",
        (device_id1, "FilterSign", "ON", now - 500, None),
    )

    # Create alert for device 2
    cursor.execute(
        "INSERT INTO alerts (device_id, alert_type, alert_value, start_time, end_time) VALUES (?, ?, ?, ?, ?)",
        (device_id2, "ErrorSign", "ON", now - 200, None),
    )

    conn.commit()

    # Get alerts for device 1 only
    alerts = db.get_alerts_for_device(conn, device_id1)

    assert len(alerts) == 2
    # Should be sorted by start_time DESC, so most recent first
    assert alerts[0]["alert_type"] == "Filter warning"
    assert alerts[1]["alert_type"] == "Error"
