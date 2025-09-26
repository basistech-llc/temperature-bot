"""
test program
"""

import json
import requests
from airthings_secrets import CLIENT_ID, CLIENT_SECRET

# Replace with your Airthings OAuth app credentials
#CLIENT_ID = "YOUR_CLIENT_ID"
#CLIENT_SECRET = "YOUR_CLIENT_SECRET"
TOKEN_URL = "https://accounts-api.airthings.com/v1/token"
#DEVICES_URL = "https://ext-api.airthings.com/v1/devices"
#SENSORS_URL = "https://ext-api.airthings.com/v1/sensors"
ACCOUNTS_URL = "https://consumer-api.airthings.com/v1/accounts"
DEVICES_URL = "https://consumer-api.airthings.com/v1/accounts/{accountId}/devices"
SENSORS_URL = "https://consumer-api.airthings.com/v1/accounts/{accountId}/sensors?{sn_param}"
TIMEOUT=5

accountId='d2712c92-9569-47b9-99c5-799ab4199b04'


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
    print("response.json():",response.json())
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
    print("url:",url)
    response = requests.get(url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()

    r = response.json().get("results")
    print(json.dumps(r,indent=4))
    return r

def get_temperature_from_device(device):
    """
    Extract the current temperature from a device's sensor data.
    """
    for sensor in device.get('currentValues', []):
        if sensor['type'] == 'temp':
            return sensor['value']
    return None

def main():
    # Get an access token
    access_token = get_access_token(CLIENT_ID, CLIENT_SECRET)

    accountId = get_account(access_token)
    print("account:",accountId)

    # Get the list of devices
    devices = get_devices(access_token,accountId)
    if not devices:
        print("No devices found.")
    print("devices:",devices)

    # Get all of the serial numbers
    sn = [dev['serialNumber'] for dev in devices]
    print("Serial Numbers:",sn)

    sensors = get_sensors(access_token, accountId, sn)
    if not devices:
        print("No sensors found.")
    print('sensors',sensors)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
