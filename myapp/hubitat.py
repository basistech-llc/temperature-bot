"""
Hubitat implementation
"""

import json
import requests
from myapp.util import get_config,get_secret
from myapp.paths import TIMEOUT_SECONDS

HUBITAT_GET_ALL_DEVICES_FULL_DETAILS = "http://{host}/apps/api/493/devices/all?access_token={access_token}"
HUBITAT_GET_DEVICE_INFO = "http://{host}/apps/api/493/devices/{device_id}?access_token={access_token}"
HUBITAT_GET_DEVICE_EVENT_HISTORY = "http://{host}/apps/api/493/devices/{device_id}/events?access_token={access_token}"
HUBITAT_GET_DEVICE_COMMANDS = "http://{host}/apps/api/493/devices/{device_id}/commands?access_token={access_token}"
HUBITAT_GET_DEVICE_CAPABILITIES="http://{host}/apps/api/493/devices/{device_id}/capabilities?access_token={access_token}"
HUBITAT_GET_DEVICE_ATTRIBUTE="http://{host}/apps/api/493/devices/{device_id}/attribute/{attribute}?access_token={access_token}"
HUBITAT_SEND_DEVICE_COMMAND="http://{host}/apps/api/493/devices/{device_id}/{command}/{secondary_value}?access_token={access_token}"
HUBITAT_POST_URL="http://{host}/apps/api/493/postURL/{url}?access_token={access_token}"

def extract_temperatures(hubdict: dict):
    """Given the full details from the hubitat, extract all the temperatures"""
    return [{'name': dev['name'], 'temperature':dev['attributes']['temperature'], 'room':dev['room']} for dev in hubdict
            if "TemperatureMeasurement" in dev['capabilities']]

def get_all_devices():
    host = get_config()['hubitat']['host']
    access_token = get_secret('hubitat','access_token')
    r = requests.get(HUBITAT_GET_ALL_DEVICES_FULL_DETAILS.format(host=host,access_token=access_token),timeout=TIMEOUT_SECONDS)
    return r.json()

if __name__=="__main__":
    """A little test program"""
    devs = get_all_devices()
    print(json.dumps(devs,indent=4))
    print(json.dumps(extract_temperatures(devs),indent=4))
