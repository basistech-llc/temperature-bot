"""
async and sync impelemntation of AirNow AQI API.
You need an API key
"""

import logging

import requests
import httpx
from myapp.util import get_config,get_secret
from myapp.paths import TIMEOUT_SECONDS

AQI_URL = "https://www.airnowapi.org/aq/observation/zipCode/current/?format=application/json&zipCode={zipcode}&distance=15&API_KEY={API_KEY}"

# https://docs.airnowapi.org/aq101
AQI_TABLE = [
    (0, 50, "Good", "Green", "#00e400", 1),
    (51, 100, "Moderate", "Yellow", "#ffff00", 2),
    (101, 150, "Unhealthy for Sensitive Groups", "Orange", "#ff7e00", 3),
    (151, 200, "Unhealthy", "Red", "#ff0000", 4),
    (201, 300, "Very Unhealthy", "Purple", "#8f3f97", 5),
    (301, 500, "Hazardous", "Maroon", "#7e0023", 6),
]


class AirnowError(Exception):
    """Generic errors"""



def aqi_color(aqi):
    for row in AQI_TABLE:
        if row[0] <= aqi <= row[1]:
            return (row[2], row[4])
    raise ValueError(f"invalid aqi={aqi}")

def get_aqi_sync():
    zipcode = get_config()['location']['zipcode']
    API_KEY = get_secret('airnow','api_key')
    url = AQI_URL.format(zipcode=zipcode, API_KEY=API_KEY)
    try:
        r = requests.get(url, timeout=TIMEOUT_SECONDS)
        aqi = r.json()[0]["AQI"]
        (name, color) = aqi_color(aqi)
        return {"value": aqi, "color": color, "name": name}
    except requests.exceptions.Timeout as e:
        raise AirnowError("timeout") from e


async def get_aqi_async():
    zipcode = get_config()['location']['zipcode']
    API_KEY = get_secret('airnow','api_key')
    url = AQI_URL.format(zipcode=zipcode,API_KEY=API_KEY)
    logging.info("get_aqi_async: %s" , url)
    async with httpx.AsyncClient( timeout=TIMEOUT_SECONDS) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.TimeoutException as e:
            raise AirnowError("timeout") from e

    if response.json()==[]:
        return {"value":"n/a", "color":"red", "name":"limited"}
    aqi = response.json()[0]['AQI']
    (name, color) = aqi_color(aqi)
    return {"value": aqi, "color": color, "name": name}
