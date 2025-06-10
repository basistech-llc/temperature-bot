import requests

# Replace with your Airthings OAuth app credentials
from airthings_secrets import CLIENT_ID, CLIENT_SECRET
#CLIENT_ID = "YOUR_CLIENT_ID"
#CLIENT_SECRET = "YOUR_CLIENT_SECRET"
TOKEN_URL = "https://accounts-api.airthings.com/v1/token"
DEVICES_URL = "https://ext-api.airthings.com/v1/devices/current-values"

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
    response = requests.post(TOKEN_URL, data=payload)
    response.raise_for_status()
    print("response.json():",response.json())
    return response.json().get('access_token')

def get_devices_with_current_values(access_token):
    """
    Get the list of devices along with their current sensor values.
    """
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(DEVICES_URL, headers=headers)
    response.raise_for_status()
    return response.json().get('data', [])

def main():
    # Get an access token
    access_token = get_access_token(CLIENT_ID, CLIENT_SECRET)

    # Get devices with current sensor values
    devices = get_devices_with_current_values(access_token)

    if not devices:
        print("No devices found.")
        return

    print("Air Monitors and Current Temperatures:")
    for device in devices:
        segment_name = device.get('segment', {}).get('name', 'Unknown Location')
        current_values = device.get('currentValues', {})
        temperature = current_values.get('temp')  # Temperature stored in 'temp'

        if temperature is not None:
            print(f"{segment_name}: {temperature}°C")
        else:
            print(f"{segment_name}: Temperature data not available.")

if __name__ == "__main__":
    main()
