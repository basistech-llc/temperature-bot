"""
Mock helpers for consistent test mocking patterns.
"""
import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import Mock


class MockHelper:
    """Helper class for setting up common mocks."""
    
    @staticmethod
    def setup_weather_mocks(mock_get_airquality, mock_get_weather_data, 
                           aqi_value: int = 45, temperature: int = 32):
        """Setup common weather and AQI mocks."""
        mock_get_airquality.return_value = aqi_value
        mock_get_weather_data.return_value = {
            "current": {"temperature": temperature, "conditions": "Sunny"},
            "forecast": []
        }
    
    @staticmethod
    def setup_ae200_mocks(mock_get_devices, mock_get_device_info, 
                          test_data_dir: str, device_id: int = 10):
        """Setup common AE200 device mocks."""
        # Load test data
        with open(Path(test_data_dir) / 'get_devices.json') as f:
            mock_get_devices.return_value = json.load(f)
        
        with open(Path(test_data_dir) / f'get_device_{device_id}.json') as f:
            mock_get_device_info.return_value = json.load(f)
    
    @staticmethod
    def create_mock_device_info_response(speed_name: str, test_data_dir: str, device_id: int = 10) -> Dict[str, Any]:
        """Create a mock device info response with a specific speed."""
        with open(Path(test_data_dir) / f'get_device_{device_id}.json') as f:
            dev_data = json.load(f)
            dev_data['FanSpeed'] = speed_name
            return dev_data
    
    @staticmethod
    def setup_ae200_device_mocks(mock_get_devices, mock_get_device_info, mock_set_fan_speed,
                                 test_data_dir: str, device_id: int = 10):
        """Setup comprehensive AE200 device mocks."""
        MockHelper.setup_ae200_mocks(mock_get_devices, mock_get_device_info, test_data_dir, device_id)
        mock_set_fan_speed.return_value = None  # set_fan_speed doesn't return anything
    
    @staticmethod
    def setup_ae200_drive_mocks(mock_get_devices, mock_get_device_info, mock_set_drive,
                               test_data_dir: str, device_id: int = 10):
        """Setup AE200 drive control mocks."""
        MockHelper.setup_ae200_mocks(mock_get_devices, mock_get_device_info, test_data_dir, device_id)
        mock_set_drive.return_value = None  # set_drive doesn't return anything
    
    @staticmethod
    def create_mock_weather_data(temperature: int = 32, conditions: str = "Sunny") -> Dict[str, Any]:
        """Create mock weather data for testing."""
        return {
            "current": {"temperature": temperature, "conditions": conditions},
            "forecast": []
        }
    
    @staticmethod
    def create_mock_aqi_data(aqi_value: int = 45) -> int:
        """Create mock AQI data for testing."""
        return aqi_value


class TestDataFactory:
    """Factory for creating consistent test data."""
    
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
