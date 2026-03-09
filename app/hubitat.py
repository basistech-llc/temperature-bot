"""
Hubitat implementation
"""

import json
import requests
from app.util import get_config,get_secret
from app.paths import TIMEOUT_SECONDS

OFFLINE = 'OFFLINE - '

HUBITAT_GET_ALL_DEVICES_FULL_DETAILS = "http://{host}/apps/api/{appId}/devices/all?access_token={access_token}"
HUBITAT_GET_DEVICE_INFO = "http://{host}/apps/api/{appId}/devices/{device_id}?access_token={access_token}"
HUBITAT_GET_DEVICE_EVENT_HISTORY = "http://{host}/apps/api/{appId}/devices/{device_id}/events?access_token={access_token}"
HUBITAT_GET_DEVICE_COMMANDS = "http://{host}/apps/api/{appId}/devices/{device_id}/commands?access_token={access_token}"
HUBITAT_GET_DEVICE_CAPABILITIES="http://{host}/apps/api/{appId}/devices/{device_id}/capabilities?access_token={access_token}"
HUBITAT_GET_DEVICE_ATTRIBUTE="http://{host}/apps/api/{appId}/devices/{device_id}/attribute/{attribute}?access_token={access_token}"
HUBITAT_SEND_DEVICE_COMMAND="http://{host}/apps/api/{appId}/devices/{device_id}/{command}/{secondary_value}?access_token={access_token}"
HUBITAT_POST_URL="http://{host}/apps/api/{appId}/postURL/{url}?access_token={access_token}"


def _coerce_numeric(value):
    """Best-effort conversion of Hubitat string numbers to Python numbers."""
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return value
        try:
            # Preserve integers when possible, otherwise float.
            if "." in s:
                return float(s)
            return int(s)
        except ValueError:
            return value
    return value


def extract_temperatures(hubdict: dict):
    """Given the full details from the hubitat, extract all the temperatures.

    Returns a list of lightweight status dicts that are suitable for both
    display and persistence in ``devlog.status_json``. We intentionally
    preserve the key Hubitat fields so downstream code can surface additional
    metrics (humidity, illuminance, battery, etc.) without needing to call
    Hubitat again.
    """
    temps: list[dict] = []
    for dev in hubdict:
        if "TemperatureMeasurement" not in dev.get("capabilities", []):
            continue

        raw_attrs = dev.get("attributes") or {}
        attrs = dict(raw_attrs)

        # Normalize common numeric attributes so downstream code can
        # rely on numbers instead of parsing strings on every use.
        for key in ("temperature", "humidity", "illuminance", "ultravioletIndex", "battery"):
            if key in attrs:
                attrs[key] = _coerce_numeric(attrs[key])

        temperature = attrs.get("temperature")

        # Skip devices that do not currently report a temperature value.
        if temperature is None:
            continue

        status = {
            # Core identity / location
            "name": dev.get("name"),
            "label": dev.get("label"),
            "room": dev.get("room"),
            "id": dev.get("id"),
            "type": dev.get("type"),
            # Capabilities and all raw attributes from Hubitat.
            "capabilities": dev.get("capabilities", []),
            "attributes": attrs,
            # Convenience top-level copies of common metrics so frontends
            # don't need to know the Hubitat schema.
            "temperature": temperature,
            "humidity": attrs.get("humidity"),
            "illuminance": attrs.get("illuminance"),
            "motion": attrs.get("motion"),
            "battery": attrs.get("battery"),
            "powerSource": attrs.get("powerSource"),
            "ultravioletIndex": attrs.get("ultravioletIndex"),
            "tamper": attrs.get("tamper"),
        }

        temps.append(
            {
                # Historical behavior: keep these top-level keys for callers
                # that only care about temperature or name.
                "name": dev.get("name"),
                "room": dev.get("room"),
                "temperature": temperature,
                # New: richer status payload suitable for status_json.
                "status": status,
            }
        )

    return temps

def get_all_devices():
    try:
        host = get_config()['hubitat']['host']
        appId = get_config()['hubitat']['appId']
    except KeyError as e:
        raise RuntimeError("hubitat config needs host and appId") from e
    access_token = get_secret('hubitat','access_token')
    r = requests.get(HUBITAT_GET_ALL_DEVICES_FULL_DETAILS.format(host=host,appId=appId,access_token=access_token),timeout=TIMEOUT_SECONDS)
    r.raise_for_status()
    data = r.json()

    # Sometimes hubitat changes name to 'offline' ... remove that
    for dev in data:
        if dev['name'].startswith(OFFLINE):
            dev['name'] = dev['name'].replace(OFFLINE,'')
    return data


def get_name_to_label():
    """Return a mapping of device name -> display label from Hubitat. Empty dict on error."""
    name_to_label = {}
    try:
        devices = get_all_devices()
        name_to_label = {
            dev["name"]: (dev.get("label") or dev["name"])
            for dev in devices
        }
    except (ValueError, RuntimeError, OSError):
        pass
    return name_to_label


if __name__=="__main__":
    """A little test program"""
    devs = get_all_devices()
    print(json.dumps(devs,indent=4))
    print(json.dumps(extract_temperatures(devs),indent=4))
