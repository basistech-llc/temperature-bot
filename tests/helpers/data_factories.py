"""
Test data factories for creating consistent test data.
"""

import json
import time
from typing import Dict, Any, Optional
from app import db


def alert_spec(
    alert_type: str,
    status_json: Dict[str, Any],
    alert_start_time: int,
    alert_value: str = "ON",
    end_time: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a dict suitable for create_device_with_alert(conn, device_name, spec)."""
    out: Dict[str, Any] = {
        "alert_type": alert_type,
        "status_json": status_json,
        "alert_start_time": alert_start_time,
        "alert_value": alert_value,
        "end_time": end_time,
    }
    return out


class TestDataFactory:
    """Factory for creating consistent test data."""

    @staticmethod
    def create_broadway_south_device(conn, ae200_device_id: int = 10) -> int:
        """Create Broadway Test device for testing."""
        device_id = db.get_or_create_device_id(conn, "Broadway Test")
        c = conn.cursor()
        c.execute(
            "UPDATE devices set ae200_device_id=? where device_id=?",
            (ae200_device_id, device_id),
        )
        conn.commit()
        return device_id

    @staticmethod
    def create_device_with_status(
        conn,
        device_name: str,
        status_dict: Dict[str, Any],
        logtime: Optional[int] = None,
    ) -> int:
        """Create a device with initial status data."""
        if logtime is None:
            logtime = int(time.time())

        device_id = db.get_or_create_device_id(conn, device_name)
        db.insert_devlog_entry(
            conn,
            device_id=device_id,
            temp=float(status_dict.get("InletTemp", 24.0)),
            statusdict=status_dict,
            logtime=logtime,
            force=True,
        )
        return device_id

    @staticmethod
    def create_mock_weather_data(temperature: int = 32) -> Dict[str, Any]:
        """Create mock weather data for testing."""
        return {
            "current": {"temperature": temperature, "conditions": "Sunny"},
            "forecast": [],
        }

    @staticmethod
    def create_mock_aqi_data() -> int:
        """Create mock AQI data for testing."""
        return 45

    @staticmethod
    def create_broadway_south_initial_status() -> Dict[str, Any]:
        """Create initial status data for Broadway Test device."""
        return {"Drive": "ON", "FanSpeed": "LOW", "InletTemp": "24.0"}

    @staticmethod
    def create_no_speed_device_status() -> Dict[str, Any]:
        """Create status data for a device without speed control."""
        return {"Drive": "ON", "InletTemp": "22.0"}

    @staticmethod
    def create_speed_mapping() -> Dict[int, str]:
        """Create mapping of speed numbers to names."""
        return {1: "LOW", 2: "MID2", 3: "MID1", 4: "HIGH"}

    @staticmethod
    def create_drive_mapping() -> Dict[int, str]:
        """Create mapping of drive numbers to names."""
        return {0: "OFF", 1: "ON"}


class DeviceTestData:
    """Test data specifically for device testing."""

    BROADWAY_SOUTH_AE200_ID = 10
    TEST_TEMP = 32

    @staticmethod
    def get_initial_status() -> Dict[str, Any]:
        """Get initial status for Broadway Test."""
        return {"Drive": "ON", "FanSpeed": "LOW", "InletTemp": "24.0"}

    @staticmethod
    def get_no_speed_status() -> Dict[str, Any]:
        """Get status for device without speed control."""
        return {"Drive": "ON", "InletTemp": "22.0"}

    @staticmethod
    def get_speed_names() -> Dict[int, str]:
        """Get speed number to name mapping."""
        return {1: "LOW", 2: "MID2", 3: "MID1", 4: "HIGH"}

    @staticmethod
    def get_drive_names() -> Dict[int, str]:
        """Get drive number to name mapping."""
        return {0: "OFF", 1: "ON"}


class WeatherTestData:
    """Test data specifically for weather testing."""

    @staticmethod
    def get_mock_weather(
        temperature: int = 32, conditions: str = "Sunny"
    ) -> Dict[str, Any]:
        """Get mock weather data."""
        return {
            "current": {"temperature": temperature, "conditions": conditions},
            "forecast": [],
        }

    @staticmethod
    def get_mock_aqi(aqi_value: int = 45) -> int:
        """Get mock AQI value."""
        return aqi_value


class AlertTestData:
    """Test data specifically for alert testing."""

    @staticmethod
    def alert_types() -> list:
        """Return supported alert type names."""
        return ["ErrorSign", "FilterSign", "CheckWater"]

    @staticmethod
    def create_device_with_alert(
        conn,
        device_name: str,
        spec: Dict[str, Any],
    ) -> int:
        """
        Create a device with a status entry and an associated alert.

        :param conn: Database connection
        :param device_name: Name for the device
        :param spec: Dict with alert_type, status_json, alert_start_time, and optionally alert_value ("ON"), end_time (None)
        :return: device_id
        """
        alert_type = spec["alert_type"]
        status_json = spec["status_json"]
        alert_start_time = spec["alert_start_time"]
        alert_value = spec.get("alert_value", "ON")
        end_time = spec.get("end_time")

        cursor = conn.cursor()
        cursor.execute("INSERT INTO devices (device_name) VALUES (?)", (device_name,))
        device_id = cursor.lastrowid

        # Create status entry
        cursor.execute(
            "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
            (device_id, alert_start_time, 600, 250, json.dumps(status_json)),
        )

        # Create alert
        cursor.execute(
            "INSERT INTO alerts (device_id, alert_type, alert_value, start_time, end_time) VALUES (?, ?, ?, ?, ?)",
            (device_id, alert_type, alert_value, alert_start_time, end_time),
        )

        conn.commit()
        return device_id
