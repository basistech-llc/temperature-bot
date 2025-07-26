"""
Weather functions from the US National Weather Service
"""

import datetime
import logging
import json
import requests

from app.util import get_config
from app.paths import TIMEOUT_SECONDS
logger = logging.getLogger(__name__)


class WeatherService:
    """Create a connection for a specific location"""
    def __init__(self, latitude=None, longitude=None):
        if latitude is None:
            latitude = get_config()['location']['latitude']
        if longitude is None:
            longitude = get_config()['location']['longitude']
        self.latitude = latitude
        self.longitude = longitude
        self.weather_points = None
        self.session = None

    def ensure_points_loaded(self):
        if self.weather_points is None:
            if self.session is None:
                self.session = requests.Session()
                self.session.timeout = TIMEOUT_SECONDS

            weather_points_url = f'https://api.weather.gov/points/{self.latitude},{self.longitude}'
            response = self.session.get(weather_points_url)
            response.raise_for_status()
            self.weather_points = response.json()

    def get_current_conditions(self):
        """Get current weather conditions from nearest station"""
        self.ensure_points_loaded()

        observation_stations_url = self.weather_points['properties']['observationStations']
        response = self.session.get(observation_stations_url)
        logger.debug("get %s",observation_stations_url)
        response.raise_for_status()
        stations = response.json()

        if not stations['features']:
            return None

        nearest_station = stations['features'][0]
        station_id = nearest_station['properties']['stationIdentifier']

        observations_url = f"https://api.weather.gov/stations/{station_id}/observations/latest"
        logger.debug("get %s",observations_url)
        response = self.session.get(observations_url)
        response.raise_for_status()
        observation = response.json()

        if not observation['properties']:
            return None

        props = observation['properties']

        return {
            'temperature': props.get('temperature', {}).get('value'),
            'conditions': props.get('textDescription', 'Unknown'),
            'icon': props.get('icon', ''),
            'station_name': nearest_station['properties']['name']
        }

    def get_forecast(self):
        """Get hourly forecast data"""
        self.ensure_points_loaded()

        forecast_hourly_url = self.weather_points['properties']['forecastHourly']
        response = self.session.get(forecast_hourly_url)
        response.raise_for_status()
        forecasts = response.json()

        forecast_data = []
        for period in forecasts['properties']['periods']:
            start_time = datetime.datetime.fromisoformat(period['startTime'])
            end_time = datetime.datetime.fromisoformat(period['endTime'])

            if end_time < datetime.datetime.now(tz=end_time.tzinfo):
                continue

            forecast_data.append({
                'time': start_time.strftime('%H:%M'),
                'temperature': period['temperature'],
                'conditions': period['shortForecast'],
                'icon': period['icon']
            })

            if len(forecast_data) >= 4:
                break

        return forecast_data

    def get_all_weather_data(self):
        """Get both current conditions and forecast"""
        current = self.get_current_conditions()
        forecast = self.get_forecast()

        return {
            'current': current,
            'forecast': forecast
        }

    def close(self):
        if self.session:
            self.session.close()


def get_weather_data(latitude=None, longitude=None):
    """Get both current weather and forecast data"""
    try:
        service = WeatherService(latitude=latitude, longitude=longitude)
        try:
            return service.get_all_weather_data()
        finally:
            service.close()
    except requests.exceptions.ConnectionError as e:
        logger.error("%s: %s", type(e), e)
        return {'error': f"{type(e)}: {e}"}
    except requests.exceptions.HTTPError as e:
        logger.error("%s: %s", type(e), e)
        return {'error': f"{type(e)}: {e}"}


if __name__=="__main__":
    info = get_weather_data()
    print(json.dumps(info, indent=4))
