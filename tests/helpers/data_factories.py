"""
Test data factories for creating consistent test data.
"""

import json
import time
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from app import db
from app.models import StatusPayload, WeatherData, json_ready


class AlertSpec(BaseModel):
    """Validated alert fixture passed to create_device_with_alert."""

    alert_type: str
    status_json: StatusPayload
    alert_start_time: int
    alert_value: str = "ON"
    end_time: int | None = Field(default=None)


def alert_spec(
    alert_type: str,
    status_json: Dict[str, Any],
    alert_start_time: int,
    alert_value: str = "ON",
    end_time: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a dict suitable for create_device_with_alert(conn, device_name, spec)."""
    return json_ready(
        AlertSpec(
            alert_type=alert_type,
            status_json=StatusPayload.model_validate(status_json),
            alert_start_time=alert_start_time,
            alert_value=alert_value,
            end_time=end_time,
        )
    )


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
    def create_erv_broadway_device(conn, ae200_device_id: int = 10) -> int:
        """Create ERV Broadway Test device for testing (appears in ERV table with radios 0-4)."""
        device_id = db.get_or_create_device_id(conn, "ERV Broadway Test")
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
        status_payload = StatusPayload.model_validate(status_dict).model_dump()

        device_id = db.get_or_create_device_id(conn, device_name)
        db.insert_devlog_entry(
            conn,
            device_id=device_id,
            temp=float(status_payload.get("InletTemp", 24.0)),
            statusdict=status_payload,
            logtime=logtime,
            force=True,
        )
        return device_id

    @staticmethod
    def create_mock_weather_data(temperature: int = 32) -> Dict[str, Any]:
        """Create mock weather data for testing."""
        return json_ready(
            WeatherData(forecast=[{"temperature": temperature, "conditions": "Sunny"}])
        )

    @staticmethod
    def create_mock_aqi_data() -> int:
        """Create mock AQI data for testing."""
        return 45

    @staticmethod
    def create_broadway_south_initial_status() -> Dict[str, Any]:
        """Create initial status data for Broadway Test device."""
        return StatusPayload.model_validate(
            {"Drive": "ON", "FanSpeed": "LOW", "InletTemp": "24.0"}
        ).model_dump()

    @staticmethod
    def create_no_speed_device_status() -> Dict[str, Any]:
        """Create status data for a device without speed control."""
        return StatusPayload.model_validate(
            {"Drive": "ON", "InletTemp": "22.0"}
        ).model_dump()

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
        return TestDataFactory.create_broadway_south_initial_status()

    @staticmethod
    def get_no_speed_status() -> Dict[str, Any]:
        """Get status for device without speed control."""
        return TestDataFactory.create_no_speed_device_status()

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
        return json_ready(
            WeatherData(forecast=[{"temperature": temperature, "conditions": conditions}])
        )

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
