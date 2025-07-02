"""
Hubitat implementation
"""

import requests
import json
from .paths import SECRETS_FILE

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
    with open(SECRETS_FILE,'r') as f:
        hubitat = json.load(f)['HUBITAT'][0]
    r = requests.get(HUBITAT_GET_ALL_DEVICES_FULL_DETAILS.format(host=hubitat['host'],access_token=hubitat['access_token']))
    return r.json()


if __name__=="__main__":
    """A little test program"""
    devs = get_all_devices()
    print(json.dumps(devs,indent=4))
    print(json.dumps(extract_temperatures(devs),indent=4))
