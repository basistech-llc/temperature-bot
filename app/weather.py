"""
Weather functions from the US National Weather Service
"""

import datetime
import logging
import json
from typing import Any

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
        self.weather_points: dict[str, Any] | None = None
        self.session: Any | None = None

    def ensure_points_loaded(self):
        if self.weather_points is None:
            if self.session is None:
                self.session = requests.Session()

            weather_points_url = f'https://api.weather.gov/points/{self.latitude},{self.longitude}'
            response = self.session.get(weather_points_url, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            self.weather_points = response.json()

    def points_and_session(self):
        """Return loaded weather points and session."""
        self.ensure_points_loaded()
        assert self.weather_points is not None
        assert self.session is not None
        return self.weather_points, self.session

    def get_current_conditions(self, num_stations=2):
        """Get current weather conditions from nearest stations.

        Returns a list of dicts, one per station.
        """
        weather_points, session = self.points_and_session()

        observation_stations_url = weather_points['properties']['observationStations']
        response = session.get(observation_stations_url, timeout=TIMEOUT_SECONDS)
        logger.debug("get %s", observation_stations_url)
        response.raise_for_status()
        stations = response.json()

        if not stations['features']:
            return []

        results = []
        for feature in stations['features'][:num_stations]:
            station_id = feature['properties']['stationIdentifier']
            station_name = feature['properties']['name']
            try:
                observations_url = f"https://api.weather.gov/stations/{station_id}/observations/latest"
                logger.debug("get %s", observations_url)
                response = session.get(observations_url, timeout=TIMEOUT_SECONDS)
                response.raise_for_status()
                observation = response.json()

                props = observation.get('properties') or {}
                results.append({
                    'temperature': (props.get('temperature') or {}).get('value'),
                    'conditions': props.get('textDescription', 'Unknown'),
                    'icon': props.get('icon', ''),
                    'station_name': station_name,
                })
            except (requests.exceptions.RequestException, KeyError, ValueError) as e:
                logger.warning("Failed to get observations for %s: %s", station_id, e)

        return results

    def get_forecast(self):
        """Get hourly forecast data"""
        weather_points, session = self.points_and_session()

        forecast_hourly_url = weather_points['properties']['forecastHourly']
        response = session.get(forecast_hourly_url, timeout=TIMEOUT_SECONDS)
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

            if len(forecast_data) >= 5:
                break

        return forecast_data

    def get_daily_forecast(self, num_periods=5):
        """Get daily forecast periods (e.g. 'Tonight', 'Monday', 'Monday Night')."""
        weather_points, session = self.points_and_session()

        forecast_url = weather_points['properties']['forecast']
        response = session.get(forecast_url, timeout=TIMEOUT_SECONDS)
        logger.debug("get %s", forecast_url)
        response.raise_for_status()
        forecasts = response.json()

        daily_data = []
        for period in forecasts['properties']['periods'][:num_periods]:
            daily_data.append({
                'name': period['name'],
                'temperature': period['temperature'],
                'conditions': period['shortForecast'],
            })

        return daily_data

    def get_all_weather_data(self):
        """Get current conditions, hourly forecast, and daily forecast"""
        stations = self.get_current_conditions()
        forecast = self.get_forecast()
        daily = self.get_daily_forecast()

        return {
            'stations': stations,
            'forecast': forecast,
            'daily': daily,
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
