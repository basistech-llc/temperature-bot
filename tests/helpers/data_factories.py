"""
Test data factories for creating consistent test data.
"""
import time
from typing import Dict, Any, Optional
from app import db


class TestDataFactory:
    """Factory for creating consistent test data."""

    @staticmethod
    def create_broadway_south_device(conn, ae200_device_id: int = 10) -> int:
        """Create Broadway Test device for testing."""
        device_id = db.get_or_create_device_id(conn, "Broadway Test")
        c = conn.cursor()
        c.execute("UPDATE devices set ae200_device_id=? where device_id=?", (ae200_device_id, device_id))
        conn.commit()
        return device_id

    @staticmethod
    def create_device_with_status(conn, device_name: str,
                                status_dict: Dict[str, Any], logtime: Optional[int] = None) -> int:
        """Create a device with initial status data."""
        if logtime is None:
            logtime = int(time.time())

        device_id = db.get_or_create_device_id(conn, device_name)
        db.insert_devlog_entry(
            conn,
            device_id=device_id,
            temp=float(status_dict.get('InletTemp', 24.0)),
            statusdict=status_dict,
            logtime=logtime,
            force=True
        )
        return device_id

    @staticmethod
    def create_mock_weather_data(temperature: int = 32) -> Dict[str, Any]:
        """Create mock weather data for testing."""
        return {
            "current": {"temperature": temperature, "conditions": "Sunny"},
            "forecast": []
        }

    @staticmethod
    def create_mock_aqi_data() -> int:
        """Create mock AQI data for testing."""
        return 45

    @staticmethod
    def create_broadway_south_initial_status() -> Dict[str, Any]:
        """Create initial status data for Broadway Test device."""
        return {
            "Drive": "ON",
            "FanSpeed": "LOW",
            "InletTemp": "24.0"
        }

    @staticmethod
    def create_no_speed_device_status() -> Dict[str, Any]:
        """Create status data for a device without speed control."""
        return {
            "Drive": "ON",
            "InletTemp": "22.0"
        }

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
        return {
            "Drive": "ON",
            "FanSpeed": "LOW",
            "InletTemp": "24.0"
        }

    @staticmethod
    def get_no_speed_status() -> Dict[str, Any]:
        """Get status for device without speed control."""
        return {
            "Drive": "ON",
            "InletTemp": "22.0"
        }

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
    def get_mock_weather(temperature: int = 32, conditions: str = "Sunny") -> Dict[str, Any]:
        """Get mock weather data."""
        return {
            "current": {"temperature": temperature, "conditions": conditions},
            "forecast": []
        }

    @staticmethod
    def get_mock_aqi(aqi_value: int = 45) -> int:
        """Get mock AQI value."""
        return aqi_value
