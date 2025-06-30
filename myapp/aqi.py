import json
import os
from os.path import dirname, join
import requests
import httpx


AQI_URL = "https://www.airnowapi.org/aq/observation/zipCode/current/?format=application/json&zipCode=02144&distance=15&API_KEY={API_KEY}"
SECRETS_PATH = join(dirname(__file__), "secrets.json")

# https://docs.airnowapi.org/aq101
AQI_TABLE = [
    (0, 50, "Good", "Green", "#00e400", 1),
    (51, 100, "Moderate", "Yellow", "#ffff00", 2),
    (101, 150, "Unhealthy for Sensitive Groups", "Orange", "#ff7e00", 3),
    (151, 200, "Unhealthy", "Red", "#ff0000", 4),
    (201, 300, "Very Unhealthy", "Purple", "#8f3f97", 5),
    (301, 500, "Hazardous", "Maroon", "#7e0023", 6),
]


def get_secrets():
    with open(SECRETS_PATH, "r") as f:
        return json.load(f)

def get_secret(name):
    if name in os.environ:
        return os.environ[name]
    return get_secrets()[name]

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
    API_KEY = get_secrets()["AIRNOW_API_KEY"]
    url = AQI_URL.format(API_KEY=API_KEY)

    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    aqi = data[0]["AQI"]
    (name, color) = aqi_color(aqi)
    return {"value": aqi, "color": color, "name": name}
