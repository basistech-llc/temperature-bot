"""
Hubitat implementation
"""

import json
from copy import deepcopy
from pathlib import Path

import requests
from app.util import env_flag_enabled, get_config, get_secret
from app.paths import TIMEOUT_SECONDS

OFFLINE = 'OFFLINE - '
HUBITAT_SIMULATOR_ENV = "HUBITAT_SIMULATOR"
SIMULATOR_DIR = Path(__file__).resolve().parent / "test_data"
SIMULATOR_DEVICES_FILE = SIMULATOR_DIR / "hubitat_get_devices.json"
ATTRIBUTES_KEY = "attributes"
DEVICE_ID_KEY = "id"
LABEL_KEY = "label"
LEVEL_KEY = "level"
SPEED_KEY = "speed"
SWITCH_KEY = "switch"

HUBITAT_GET_ALL_DEVICES_FULL_DETAILS = "http://{host}/apps/api/{appId}/devices/all?access_token={access_token}"
HUBITAT_GET_DEVICE_INFO = "http://{host}/apps/api/{appId}/devices/{device_id}?access_token={access_token}"
HUBITAT_GET_DEVICE_EVENT_HISTORY = "http://{host}/apps/api/{appId}/devices/{device_id}/events?access_token={access_token}"
HUBITAT_GET_DEVICE_COMMANDS = "http://{host}/apps/api/{appId}/devices/{device_id}/commands?access_token={access_token}"
HUBITAT_GET_DEVICE_CAPABILITIES="http://{host}/apps/api/{appId}/devices/{device_id}/capabilities?access_token={access_token}"
HUBITAT_GET_DEVICE_ATTRIBUTE="http://{host}/apps/api/{appId}/devices/{device_id}/attribute/{attribute}?access_token={access_token}"
HUBITAT_POST_URL="http://{host}/apps/api/{appId}/postURL/{url}?access_token={access_token}"

# Dashboard API Constants
HUBITAT_LIST_DASHBOARDS = "http://{host}/apps/api/{appId}/dashboard/list?access_token={access_token}"
HUBITAT_DUMP_DASHBOARD = "http://{host}/apps/api/{appId}/dashboard/{dash_id}?access_token={access_token}"

HUBITAT_SEND_DEVICE_COMMAND="http://{host}/apps/api/{appId}/devices/{device_id}/{command}/{secondary_value}?access_token={access_token}"


def hubitat_simulator_enabled() -> bool:
    """Return True when Hubitat simulator mode is explicitly enabled."""
    return env_flag_enabled(HUBITAT_SIMULATOR_ENV)


def _load_simulated_devices():
    with open(SIMULATOR_DEVICES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


_SIMULATED_DEVICES = _load_simulated_devices()


def _simulated_devices():
    return deepcopy(_SIMULATED_DEVICES)


def _simulated_device(device_id):
    target = str(device_id)
    try:
        return next(
            device
            for device in _SIMULATED_DEVICES
            if str(device.get(DEVICE_ID_KEY)) == target
        )
    except StopIteration as exc:
        raise RuntimeError(f"simulated Hubitat device {target} does not exist") from exc


def reset_simulator() -> None:
    """Restore the deterministic Hubitat simulator fixture."""
    _SIMULATED_DEVICES[:] = _load_simulated_devices()


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

def get_base_params(app_id_override=None):
    """Fetch config. Use app_id_override if provided, else use Maker API ID."""
    try:
        config = get_config()
        return {
            "host": config['hubitat']['host'],
            "appId": app_id_override or config['hubitat']['appId'],
            "access_token": get_secret('hubitat', 'access_token')
        }
    except KeyError as e:
        raise RuntimeError("hubitat config needs host and appId") from e

def dump_dashboard(dash_id, access_token_override=None):
    """
    Fetches dashboard elements.
    Note: Dashboards often have their own unique access tokens.
    """
    if hubitat_simulator_enabled():
        raise RuntimeError("Hubitat dashboards are unavailable in simulator mode")
    config = get_config()
    hubitat_cfg = config.get("hubitat", {})
    dashboard_app_id = hubitat_cfg.get("dashboard_appId") or hubitat_cfg.get("appId")

    # Use a dedicated dashboard appId if configured, otherwise fall back to the main appId.
    params = get_base_params(app_id_override=dashboard_app_id)
    params["dash_id"] = dash_id

    # If a specific token was provided for this dashboard, use it
    if access_token_override:
        params["access_token"] = access_token_override

    url = HUBITAT_DUMP_DASHBOARD.format(**params)
    r = requests.get(url, timeout=TIMEOUT_SECONDS)
    r.raise_for_status()
    print(r.text)
    return r.json()

def get_all_devices():
    if hubitat_simulator_enabled():
        return _simulated_devices()
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

def send_device_command(device_id, command, secondary_value=""):
    """Send a command to a Hubitat device by ID.

    This is the low-level helper used by all device-control wrappers.
    """
    if hubitat_simulator_enabled():
        device = _simulated_device(device_id)
        attributes = device.setdefault(ATTRIBUTES_KEY, {})
        if command in {"on", "off"}:
            attributes[SWITCH_KEY] = command
        elif command == "setLevel":
            level = int(secondary_value)
            attributes[LEVEL_KEY] = level
            attributes[SWITCH_KEY] = "on" if level else "off"
        elif command == "setSpeed":
            attributes[SPEED_KEY] = str(secondary_value)
            attributes[SWITCH_KEY] = "off" if secondary_value == "off" else "on"
        else:
            raise ValueError(f"unsupported simulated Hubitat command: {command}")
        return deepcopy(device)

    params = get_base_params()
    url = HUBITAT_SEND_DEVICE_COMMAND.format(
        host=params['host'],
        appId=params['appId'],
        device_id=device_id,
        command=command,
        secondary_value=secondary_value,
        access_token=params['access_token']
    ).replace("/?", "?")

    r = requests.get(url, timeout=TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()


def get_device_info(device_id):
    """Fetch full details for a single device by ID."""
    if hubitat_simulator_enabled():
        return deepcopy(_simulated_device(device_id))
    params = get_base_params()
    url = HUBITAT_GET_DEVICE_INFO.format(
        host=params['host'],
        appId=params['appId'],
        device_id=device_id,
        access_token=params['access_token']
    )
    r = requests.get(url, timeout=TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()


def set_dimmer_level(device_id, level):
    """Set a dimmable light to the given level (0-100).

    Level 0 turns the light off; any other value turns it on at that brightness.
    """
    if level == 0:
        return send_device_command(device_id, "off")
    return send_device_command(device_id, "setLevel", str(level))


def set_switch(device_id, state):
    """Turn a switch device on or off.

    state: 'on' or 'off'
    """
    return send_device_command(device_id, state)


def set_fan_speed(device_id, speed):
    """Set a Hubitat ``FanControl`` device's speed.

    speed: one of ``off``, ``low``, ``medium``, ``high``

    Sent through ``setSpeed`` rather than on/off so the device keeps reporting a
    speed. Hubitat drivers accept more speeds than we offer; the narrower set is
    a UI choice, not a driver limit.
    """
    return send_device_command(device_id, "setSpeed", str(speed))


def _find_device_by_label(label):
    """Find a device by its Hubitat label. Raises RuntimeError if not found."""
    devices = get_all_devices()
    target = next(
        (device for device in devices if device.get(LABEL_KEY) == label), None
    )
    if not target:
        raise RuntimeError(f"Device with label '{label}' not found in Maker API.")
    return target


def control_room_tv(direction, *, up_label, down_label):
    """Activate a configured room's TV up or down component switch.

    direction: 'up' or 'down'
    """
    label = up_label if direction == "up" else down_label
    target = _find_device_by_label(label)
    return send_device_command(target[DEVICE_ID_KEY], "on")


def control_hickory_tv(direction):
    """Backward-compatible Hickory TV helper."""
    return control_room_tv(direction, up_label="TV Up", down_label="TV Down")

if __name__=="__main__":
    """A little test program"""
    import argparse
    parser = argparse.ArgumentParser(description="Hubitat CLI Tool")
    parser.add_argument("--hickory-tv", choices=["up", "down"], help="Control the Hickory TV lift")
    parser.add_argument("--list-devices", action="store_true", help="List all devices")
    parser.add_argument("--list-temperatures", action="store_true", help="List all temperatures")
    parser.add_argument("--dump-dashboard", type=int, help="Dump elements of a specific dashboard ID")

    args = parser.parse_args()

    if args.hickory_tv:
        control_hickory_tv(args.hickory_tv)
    elif args.dump_dashboard:
        elements = dump_dashboard(args.dump_dashboard)
        print(json.dumps(elements, indent=4))

    elif args.list_devices:
        print(json.dumps(extract_temperatures(get_all_devices()),indent=4))
    elif args.list_temperatures:
        print(json.dumps(extract_temperatures(get_all_devices()),indent=4))
    else:
        parser.print_help()
