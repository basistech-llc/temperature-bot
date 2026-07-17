"""Slack notification delivery."""

import logging

import requests
from pydantic import BaseModel

from app.paths import TIMEOUT_SECONDS
from app.util import get_secret

logger = logging.getLogger(__name__)

SLACK_POST_URL = "https://slack.com/api/chat.postMessage"
SLACK_UPDATE_URL = "https://slack.com/api/chat.update"
SLACK_CHANNEL_KEY = "channel"
SLACK_TEXT_KEY = "text"
SLACK_TIMESTAMP_KEY = "ts"


class SlackApiResponse(BaseModel):
    """Fields used from Slack's response envelope."""

    ok: bool
    ts: str | None = None
    error: str | None = None


def post(message: str, channel: str | None = None, message_ts: str | None = None) -> str:
    """Post or update a Slack message and return its timestamp."""
    token = get_secret("slack", "token")
    destination = channel or get_secret("slack", "channel")
    url = SLACK_UPDATE_URL if message_ts is not None else SLACK_POST_URL
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        SLACK_CHANNEL_KEY: destination,
        SLACK_TEXT_KEY: message,
    }
    if message_ts is not None:
        payload[SLACK_TIMESTAMP_KEY] = message_ts

    response = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    result = SlackApiResponse.model_validate(response.json())
    if not result.ok:
        raise RuntimeError(f"Slack API error: {result.error or 'unknown error'}")
    if not result.ts:
        raise RuntimeError("Slack API response did not include a message timestamp")
    return result.ts
