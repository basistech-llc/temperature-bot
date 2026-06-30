"""
Slack implementation
"""

import logging
import requests
from app.util import get_secret

logger = logging.getLogger(__name__)

SLACK_POST_URL = "https://slack.com/api/chat.postMessage"
SLACK_UPDATE_URL = "https://slack.com/api/chat.update"

def post(message,channel=None,message_ts = None):
    url = SLACK_POST_URL
    try:
        token = get_secret('slack','token')
        if channel is None:
            channel = get_secret('slack','channel')
    except KeyError as e:
        raise RuntimeError("slack config needs token, url and possibly channel") from e
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        "channel": channel,
        "text": message
    }
    if message_ts is not None:  # edit an old message
        url = SLACK_UPDATE_URL
        payload['ts'] = message_ts

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 200:
        json_data = response.json()
        if not json_data.get("ok"):
            logger.error("Slack API Error: %s",json_data.get('error'))
        if message_ts is not None:
            message_ts = response.get('ts')
        return message_ts
    else:
        logger.error("HTTP Error %s: %s",response.status_code,response.text)
    return None
