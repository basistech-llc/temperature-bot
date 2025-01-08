import os
import datetime

from os.path import join,dirname,abspath
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Replace with the path to your service account credentials JSON file
CLIENT_SECRETS_FILE = join(dirname(abspath(__file__)),
                            'client_secret_332875224115-e7th03rq9r109gd87huniri1mfqqes0v.apps.googleusercontent.com.json')

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TOKEN_FILE='token.json'

# Replace with the ID of your Google Sheet
SPREADSHEET_ID = '18qi99tAAPu-CeuGG8bXBYTmHWJ6YX8hfBF3SSnQpqgA'

# The range where you want to append the data
RANGE_NAME = 'Sheet1!A1:G'  # Adjust sheet name and range as needed

# Authenticate using the service account
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


def append_row_to_sheet(data):
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

if __name__ == '__main__':
    # Example row data to append
    now = datetime.datetime.now()

    new_row = [now.isoformat(), 'Example', 'Data', 'For', 'New', 'Row']
    append_row_to_sheet(new_row)
