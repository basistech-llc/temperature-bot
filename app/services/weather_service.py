"""
Weather and AQI-related business logic
"""
import logging
from .. import airquality, weather, db

logger = logging.getLogger(__name__)


class WeatherService:
    """Service for weather and AQI operations"""

    def __init__(self):
        self.logger = logger

    def get_db_aqi(self, conn) -> dict:
        """
        Get AQI from database.

        :param conn: database connection
        :return: AQI data dict with value, color, name
        """
        # Check for recent AQI data in database
        c = conn.cursor()
        c.execute("SELECT aqi FROM aqi order by logtime DESC limit 1")
        row = c.fetchone()
        aqi = row[0] if row is not None else 0
        return airquality.aqi_decode(aqi)

    def get_weather_data(self, conn) -> dict:
        """Get combined weather and AQI data"""
        aqi_data = self.get_db_aqi(conn)
        weather_data = weather.get_weather_data()
        return {"aqi": aqi_data, "weather": weather_data}
