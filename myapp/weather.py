import requests
import httpx
import asyncio
import datetime
from myapp.utils import get_secret

BASIS_LAT = 42.3876
BASIS_LON = -71.0995

AQI_URL = "https://www.airnowapi.org/aq/observation/zipCode/current/?format=application/json&zipCode=02144&distance=15&API_KEY={API_KEY}"

# https://docs.airnowapi.org/aq101
AQI_TABLE = [
    (0, 50, "Good", "Green", "#00e400", 1),
    (51, 100, "Moderate", "Yellow", "#ffff00", 2),
    (101, 150, "Unhealthy for Sensitive Groups", "Orange", "#ff7e00", 3),
    (151, 200, "Unhealthy", "Red", "#ff0000", 4),
    (201, 300, "Very Unhealthy", "Purple", "#8f3f97", 5),
    (301, 500, "Hazardous", "Maroon", "#7e0023", 6),
]


def aqi_color(aqi):
    for row in AQI_TABLE:
        if row[0] <= aqi <= row[1]:
            return (row[2], row[4])


def get_aqi_sync():
    API_KEY = get_secret('AIRNOW_API_KEY')
    url = AQI_URL.format(API_KEY=API_KEY)
    r = requests.get(url)
    aqi = r.json()[0]["AQI"]
    (name, color) = aqi_color(aqi)
    return {"value": aqi, "color": color, "name": name}


async def get_aqi_async():
    API_KEY = get_secret('AIRNOW_API_KEY')
    url = AQI_URL.format(API_KEY=API_KEY)

    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    aqi = data[0]["AQI"]
    (name, color) = aqi_color(aqi)
    return {"value": aqi, "color": color, "name": name}


class WeatherService:
    def __init__(self, lat=BASIS_LAT, lon=BASIS_LON):
        self.lat = lat
        self.lon = lon
        self.weather_points = None
        self._client = None
    
    async def _ensure_points_loaded(self):
        if self.weather_points is None:
            if self._client is None:
                self._client = httpx.AsyncClient()
            
            weather_points_url = f'https://api.weather.gov/points/{self.lat},{self.lon}'
            response = await self._client.get(weather_points_url)
            response.raise_for_status()
            self.weather_points = response.json()
    
    async def get_current_conditions(self):
        """Get current weather conditions from nearest station"""
        await self._ensure_points_loaded()
        
        observation_stations_url = self.weather_points['properties']['observationStations']
        response = await self._client.get(observation_stations_url)
        response.raise_for_status()
        stations = response.json()
        
        if not stations['features']:
            return None
            
        nearest_station = stations['features'][0]
        station_id = nearest_station['properties']['stationIdentifier']
        
        observations_url = f"https://api.weather.gov/stations/{station_id}/observations/latest"
        response = await self._client.get(observations_url)
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
        await self._ensure_points_loaded()
        
        forecast_hourly_url = self.weather_points['properties']['forecastHourly']
        response = await self._client.get(forecast_hourly_url)
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
        if self._client:
            await self._client.aclose()


async def get_weather_data_async(lat=BASIS_LAT, lon=BASIS_LON):
    """Get both current weather and forecast data"""
    service = WeatherService(lat=lat, lon=lon)
    try:
        return await service.get_all_weather_data()
    finally:
        await service.close()


# Legacy functions for backward compatibility
async def get_weather_async(lat=BASIS_LAT, lon=BASIS_LON):
    """Legacy function - returns raw weather API data"""
    service = WeatherService(lat=lat, lon=lon)
    try:
        await service._ensure_points_loaded()
        
        observation_stations_url = service.weather_points['properties']['observationStations']
        forecast_hourly_url = service.weather_points['properties']['forecastHourly']
        
        stations_response, forecast_response = await asyncio.gather(
            service._client.get(observation_stations_url),
            service._client.get(forecast_hourly_url)
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

async def get_current_weather_async(lat=BASIS_LAT, lon=BASIS_LON):
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
