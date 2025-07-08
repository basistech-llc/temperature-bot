"""
Weather functions from the US National Weather Service
"""

import asyncio
import datetime
import logging
import json

import httpx
from app.util import get_config
from app.paths import TIMEOUT_SECONDS

class WeatherService:
    """Create a connection for a specific location"""
    def __init__(self, lat=None, lon=None):
        if lat is None:
            lat = get_config()['location']['lat']
        if lon is None:
            lon = get_config()['location']['lon']
        self.lat = lat
        self.lon = lon
        self.weather_points = None
        self.client = None

    async def ensure_points_loaded(self):
        if self.weather_points is None:
            if self.client is None:
                self.client = httpx.AsyncClient(timeout=TIMEOUT_SECONDS)

            weather_points_url = f'https://api.weather.gov/points/{self.lat},{self.lon}'
            response = await self.client.get(weather_points_url)
            response.raise_for_status()
            self.weather_points = response.json()

    async def get_current_conditions(self):
        """Get current weather conditions from nearest station"""
        await self.ensure_points_loaded()

        observation_stations_url = self.weather_points['properties']['observationStations']
        response = await self.client.get(observation_stations_url)
        response.raise_for_status()
        stations = response.json()

        if not stations['features']:
            return None

        nearest_station = stations['features'][0]
        station_id = nearest_station['properties']['stationIdentifier']

        observations_url = f"https://api.weather.gov/stations/{station_id}/observations/latest"
        response = await self.client.get(observations_url)
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

    async def get_forecast(self):
        """Get hourly forecast data"""
        await self.ensure_points_loaded()

        forecast_hourly_url = self.weather_points['properties']['forecastHourly']
        response = await self.client.get(forecast_hourly_url)
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

    async def get_all_weather_data(self):
        """Get both current conditions and forecast"""
        current_task = asyncio.create_task(self.get_current_conditions())
        forecast_task = asyncio.create_task(self.get_forecast())

        current, forecast = await asyncio.gather(current_task, forecast_task)

        return {
            'current': current,
            'forecast': forecast
        }

    async def close(self):
        if self.client:
            await self.client.aclose()


async def get_weather_data_async(lat=None, lon=None):
    """Get both current weather and forecast data"""
    try:
        service = WeatherService(lat=lat, lon=lon)
        try:
            return await service.get_all_weather_data()
        finally:
            await service.close()
    except httpx.ConnectError as e:
        logging.error("%s: %s",type(e),e)
        return {'error':f"{type(e)}: {e}" }
    except httpx.HTTPStatusError as e:
        logging.error("%s: %s",type(e),e)
        return {'error':f"{type(e)}: {e}" }



if __name__=="__main__":
    info = asyncio.run(get_weather_data_async())
    print(json.dumps(info,indent=4))
