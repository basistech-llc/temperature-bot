import os
import datetime

from os.path import join,dirname,abspath
import requests
import google.auth.exceptions
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
#from googleapiclient.errors import HttpError
#from googleapiclient.http import BatchHttpRequest

# Replace with the path to your service account credentials JSON file
from hubitat_secret import HUBITAT_GET_ALL_DEVICES_FULL_DETAILS

CLIENT_SECRETS_FILE = join(dirname(abspath(__file__)),
                            'client_secret_332875224115-e7th03rq9r109gd87huniri1mfqqes0v.apps.googleusercontent.com.json')

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TOKEN_FILE='token.json'

# Replace with the ID of your Google Sheet
SPREADSHEET_ID = '18qi99tAAPu-CeuGG8bXBYTmHWJ6YX8hfBF3SSnQpqgA'

# The range where you want to append the data
RANGE_NAME = 'Sheet1!A1:G'  # Adjust sheet name and range as needed

def get_creds():
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except google.auth.exceptions.RefreshError:
                print("try deleting",TOKEN_FILE)
                exit(0)
        else:
            flow = InstalledAppFlow.from_client_secrets_file( CLIENT_SECRETS_FILE, SCOPES )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return creds


def first_row():
    service = build('sheets', 'v4', credentials=get_creds())
    sheet = service.spreadsheets()
    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range='Sheet1!A1:1'  # Adjust 'Sheet1' if your sheet has a different name
    ).execute()
    values = result.get('values', [])
    try:
        return values[0]
    except (TypeError,IndexError):
        return None

def append_row(data):
    # Create a Google Sheets API client
    service = build('sheets', 'v4', credentials=get_creds())
    sheet = service.spreadsheets()

    # Append data to the sheet
    body = {'values': [data]}
    response = sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=RANGE_NAME,
        valueInputOption='RAW',
        insertDataOption='INSERT_ROWS',
        body=body
    ).execute()
    print(f"Row appended: {response}")

def update_row(n, new_row):
    """Rewrite the first row of the Google Sheet with new data."""
    if n<1 or not isinstance(n,int):
        raise ValueError(f"row {n} is invalid")

    service = build('sheets', 'v4', credentials=get_creds())
    sheet = service.spreadsheets()

    # Prepare the body for the update
    body = {'values': [new_row]}

    # Update the first row
    response = sheet.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f'Sheet1!A{n}:{n}',  # Adjust 'Sheet1' if your sheet has a different name
        valueInputOption='RAW',  # Use 'RAW' or 'USER_ENTERED'
        body=body
    ).execute()
    print(f"First row updated: {response}")


if __name__ == '__main__':
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Format as "YYYY-MM-DD HH:MM:SS"

    # Get the first row of the spreadsheet
    updated_header = False
    header = first_row()

    # Get the hubitat data
    hub_data = requests.get(HUBITAT_GET_ALL_DEVICES_FULL_DETAILS).json()
    temps = {}                  # by device

    # find all of the temps and append new header
    for e in hub_data:
        if 'temperature' in e['attributes']:
            label = e['label']
            temps[label] = e['attributes']['temperature']
            if label not in header:
                header.append(label)
                updated_header = True

    # Now prepare the data to write
    new_row = [now] + [temps.get(label,"") for label in header[1:]]
    assert len(new_row) == len(header)

    # Update the heder if the header changed and then data, which is always new
    if updated_header:
        update_row(1, header)
    append_row(new_row)
