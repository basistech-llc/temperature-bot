"""
Interface to the airthings api
"""

import os
import json
import requests
import logging
import json
import requests  # type: ignore
from pathlib import Path
from collections import defaultdict
from app.util import get_config, get_secret
from app.paths import TIMEOUT_SECONDS


TOKEN_URL = "https://accounts-api.airthings.com/v1/token"
ACCOUNTS_URL = "https://consumer-api.airthings.com/v1/accounts"
DEVICES_URL = "https://consumer-api.airthings.com/v1/accounts/{accountId}/devices"
SENSORS_URL = "https://consumer-api.airthings.com/v1/accounts/{accountId}/sensors?{sn_param}"
TIMEOUT=5

CLIENT_ID     = get_secret("airthings","client_id")
CLIENT_SECRET = get_secret("airthings","client_secret")
AIRTHINGS_SIMULATOR = os.getenv('AIRTHINGS_SIMULATOR')
AIRTHINGS_SAMPLE_FILE     = Path(__file__).parent.parent / 'etc' / 'airthings_sample.json'

def get_access_token(client_id, client_secret):
    """
    Get an OAuth2 access token using the client credentials grant type.
    """
    payload = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
        'scope': 'read:device:current_values'
    }
    response = requests.post(TOKEN_URL, data=payload, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json().get('access_token')

def get_account(access_token):
    """
    Get the list of devices associated with the account.
    """
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(ACCOUNTS_URL, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()['accounts'][0]['id']

def get_devices(access_token,accountId):
    """
    Get the list of devices associated with the account.
    """
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(DEVICES_URL.format(accountId=accountId), headers=headers, timeout=TIMEOUT)
    return response.json().get('devices', [])

def get_sensors(access_token,accountId,sn_array):
    """
    Get the list of devices associated with the account.
    """
    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    url = SENSORS_URL.format(accountId=accountId,sn_param="&".join([f"sn={_}" for _ in sn_array]))
    response = requests.get(url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()

    r = response.json().get("results")
    return r

def get_temperature_from_device(device):
    """
    Extract the current temperature from a device's sensor data.
    """
    for sensor in device.get('currentValues', []):
        if sensor['type'] == 'temp':
            return sensor['value']
    return None

# Get an access token
def read_airthings_now():
    if AIRTHINGS_SIMULATOR:
        with AIRTHINGS_SAMPLE_FILE.open() as f:
            return json.load(f)

    access_token = get_access_token(CLIENT_ID, CLIENT_SECRET)
    accountId = get_account(access_token)

    # Get the list of devices
    devices = get_devices(access_token,accountId)
    if not devices:
        raise RuntimeError("No devices found.")

    # Get all of the serial numbers
    sn_list = [dev['serialNumber'] for dev in devices]
    # Get all of the sensor readings with a single query
    sensors = get_sensors(access_token, accountId, sn_list)
    if not sensors:
        raise RuntimeError("No sensors found.")

    # Combine everything
    res = {}
    for device in devices:
        sn = device['serialNumber']
        res[sn] = device
        del res[sn]['sensors']
    for sensor in sensors:
        sn = sensor['serialNumber']
        res[sn]['sensors'] = sensor['sensors']

    return list(res.values())

if __name__ == "__main__":
    v = read_airthings_now()
    print(json.dumps(v,indent=4))
