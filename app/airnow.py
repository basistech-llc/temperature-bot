"""
Synchronous implementation of AirNow AQI API.
You need an API key
"""

import logging
import requests
from app.util import get_config, get_secret
from app.paths import TIMEOUT_SECONDS

AQI_URL = "https://www.airnowapi.org/aq/observation/zipCode/current/?format=application/json&zipCode={zipcode}&distance=15&API_KEY={API_KEY}"

logger = logging.getLogger(__name__)


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

def aqi_decode(aqi):
    aqi = int(aqi)
    for row in AQI_TABLE:
        if row[0] <= aqi <= row[1]:
            return {'value':aqi, 'name':row[2], 'color_name': row[3], 'color':row[4]}
    raise ValueError(f"aqi={aqi}")

def get_aqi():
    """Get AQI data from AirNow API synchronously"""
    zipcode = get_config()['location']['zipcode']
    API_KEY = get_secret('airnow', 'api_key')
    url = AQI_URL.format(zipcode=zipcode, API_KEY=API_KEY)
    logger.info("get_aqi: %s", url)

    try:
        r = requests.get(url, timeout=TIMEOUT_SECONDS)
        r.raise_for_status()

        if r.json() == []:
            return {"error": "AirNow API returned []; likely rate-limited"}
        return r.json()[0]["AQI"]

    except requests.exceptions.Timeout as e:
        raise AirnowError("timeout") from e
    except requests.exceptions.HTTPError as e:
        logger.error("%s: %s", type(e), e)
        return {"error": f"HTTP Status error: {e}"}
    except Exception as e:      # pylint: disable=broad-exception-caught
        logger.error("Exception in get_aqi: %s", e)
        return {"error": str(e)}
