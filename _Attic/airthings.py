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
DEVICES_URL = "https://ext-api.airthings.com/v1/devices"
SENSORS_URL = "https://ext-api.airthings.com/v1/sensors"
TIMEOUT=5

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

def get_devices(access_token):
    """
    Get the list of devices associated with the account.
    """
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(DEVICES_URL, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json().get('devices', [])

def get_sensors(access_token):
    """
    Get the list of devices associated with the account.
    """
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(DEVICES_URL, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    print(response)
    return response.json().get('devices', [])

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

    # Get the list of devices
    devices = get_devices(access_token)

    if not devices:
        print("No devices found.")
        return

    print("Air Monitors and Current Temperatures:")
    for device in devices:
        print(device)
        device_name = device.get('segment', {}).get('name', 'Unknown Device')
        current_temperature = get_temperature_from_device(device)
        if current_temperature is not None:
            print(f"{device_name}: {current_temperature}°C")
        else:
            print(f"{device_name}: Temperature data not available.")
    print(json.dumps(get_sensors(access_token),indent=4))

if __name__ == "__main__":
    main()
