"""
Weather functions from the US National Weather Service
"""

import asyncio
import datetime

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
    service = WeatherService(lat=lat, lon=lon)
    try:
        return await service.get_all_weather_data()
    finally:
        await service.close()


# Legacy functions for backward compatibility
async def get_weather_async(lat=None, lon=None):
    """Legacy function - returns raw weather API data"""
    service = WeatherService(lat=lat, lon=lon)
    try:
        await service.ensure_points_loaded()

        observation_stations_url = service.weather_points['properties']['observationStations']
        forecast_hourly_url = service.weather_points['properties']['forecastHourly']

        stations_response, forecast_response = await asyncio.gather(
            service.client.get(observation_stations_url),
            service.client.get(forecast_hourly_url)
        )

        stations_response.raise_for_status()
        forecast_response.raise_for_status()

        return {
            'points': service.weather_points,
            'stations': stations_response.json(),
            'forecasts': forecast_response.json()
        }
    finally:
        await service.close()

async def get_current_weather_async(lat=None, lon=None):
    """Legacy function - get current weather from nearest station"""
    service = WeatherService(lat=lat, lon=lon)
    try:
        return await service.get_current_conditions()
    finally:
        await service.close()

def print_weather(info, limit=None):
    # Find the closest station
    for ct,station in enumerate(info['stations']['features']):
        prop = station['properties']
        print(station['geometry']['coordinates'], prop['stationIdentifier'], prop['name'], prop['distance']['value'])
        if limit is not None and ct>=limit:
            break

    # print the forecast
    for ct,forecast in enumerate(info['forecasts']['properties']['periods']):
        start = datetime.datetime.fromisoformat(forecast['startTime'])
        end = datetime.datetime.fromisoformat(forecast['endTime'])
        if end < datetime.datetime.now(tz=end.tzinfo):
            continue
        print(start,forecast['temperature'],forecast['icon'],forecast['shortForecast'])
        if limit is not None and ct>=limit:
            break


if __name__=="__main__":
    info = asyncio.run(get_weather_async())
    print_weather(info, limit = 5)
