"""
Test data factories for creating consistent test data.
"""
import time
from typing import Dict, Any, List, Optional
from app import db


class TestDataFactory:
    """Factory for creating consistent test data."""
    
    @staticmethod
    def create_broadway_south_device(conn, ae200_device_id: int = 10) -> int:
        """Create Broadway South device for testing."""
        device_id = db.get_or_create_device_id(conn, "Broadway South")
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
        """Create initial status data for Broadway South device."""
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
    
    @staticmethod
    def create_temporal_test_data(conn, device_name: str = "Temporal Test Device") -> tuple[int, Dict[str, int]]:
        """
        Creates test data with records at different time intervals:
        - 1 hour ago
        - 26 hours ago  
        - 200 hours ago
        - 2000 hours ago

        Returns the device_id and a dict with the expected record counts for different time ranges.
        """
        current_time = int(time.time())

        # Create device
        cursor = conn.cursor()
        cursor.execute("INSERT INTO devices (device_name) VALUES (?)", (device_name,))
        device_id = cursor.lastrowid

        # Define time intervals in seconds
        intervals = {
            "1_hour": 1 * 60 * 60,
            "26_hours": 26 * 60 * 60,
            "200_hours": 200 * 60 * 60,
            "2000_hours": 2000 * 60 * 60
        }

        # Add records at each interval. Initial speed is always LOW.
        for interval_name, seconds in intervals.items():  # pylint: disable=unused-variable
            record_time = current_time - seconds
            cursor.execute("""
                INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
                VALUES (?, ?, ?, ?, ?)
            """, (device_id, record_time, 60, 240, '{"Drive": "ON", "FanSpeed": "LOW", "InletTemp": "24.0"}'))

        conn.commit()

        # Calculate expected record counts for different time ranges
        expected_counts = {
            "day": 1,    # Only 1 hour ago
            "week": 2,   # 1 hour + 26 hours ago
            "month": 3,  # 1 hour + 26 hours + 200 hours ago
            "all": 4     # All records
        }

        return device_id, expected_counts


class DeviceTestData:
    """Test data specifically for device testing."""
    
    BROADWAY_SOUTH_AE200_ID = 10
    TEST_TEMP = 32
    
    @staticmethod
    def get_initial_status() -> Dict[str, Any]:
        """Get initial status for Broadway South."""
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
