"""
Mock helpers for consistent test mocking patterns.
"""
from typing import Any, Dict


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
