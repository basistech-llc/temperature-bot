"""
API route handlers
"""

import asyncio
import logging
import time
from typing import Any

from flask import Blueprint, request, jsonify
from flask_pydantic import validate

from .constants import __version__
from . import constants
from . import db
from . import db_alerts
from . import rules_engine
from . import hubitat
from . import ae200
from .display_names import display_device_name
from . import room_config
from .utils.request_utils import parse_device_ids
from .utils.db_utils import with_db_connection

from .models import SpeedControl, DriveControl, NoteControl, SetTempControl

logger = logging.getLogger(__name__)

# Create API blueprint
api_v1 = Blueprint("api_v1", __name__)


@api_v1.route("/version")
def get_version_json():
    return jsonify({"version": __version__})


@api_v1.route("/set_fan_speed", methods=["POST"])
@validate()
@with_db_connection
def set_fan_speed(conn, body: SpeedControl):
    """Sets the speed, records the speed in the changelog,
    and then updates the database, so status is always up-to-date"""
    logger.debug("/set_fan_speed: body=[%s]", body)
    ret = rules_engine.set_body_fan_speed(conn, body, request.remote_addr, "web")
    db.disable_rules_for_device(
        conn,
        device_id=ret["device_id"],
        seconds=constants.RULES_DISABLE_SECONDS,
        ipaddr=request.remote_addr,
        agent=request.headers.get("User-Agent"),
    )
    return jsonify({"status": "ok", **ret})


@api_v1.route("/set_drive", methods=["POST"])
@validate()
@with_db_connection
def set_drive(conn, body: DriveControl):
    """Sets the speed, records the speed in the changelog, and then updates the database, so status is always up-to-date"""
    logger.debug("/set_drive: body=[%s]", body)
    ret = rules_engine.set_body_drive(conn, body, request.remote_addr, "web")
    device_id = ret["device_id"]
    db.disable_rules_for_device(
        conn,
        device_id=device_id,
        seconds=constants.RULES_DISABLE_SECONDS,
        ipaddr=request.remote_addr,
        agent=request.headers.get("User-Agent"),
        comment=f"rules for disabled for {constants.RULES_DISABLE_SECONDS / 60} minutes",
    )
    return jsonify({"status": "ok", **ret})


@api_v1.route("/set_temp", methods=["POST"])
@validate()
@with_db_connection
def set_temp(conn, body: SetTempControl):
    """Set the target temperature for a unit.

    The request body must provide `set_temp_c` in Celsius; the UI is responsible
    for converting from Fahrenheit if needed.
    """
    logger.debug("/set_temp: body=[%s]", body)
    ret = rules_engine.set_body_set_temp(conn, body, request.remote_addr, "web")
    return jsonify({"status": "ok", **ret})


@api_v1.route("/status")
@with_db_connection
def get_status(conn):
    """Get device status"""
    logger.debug("**************** /status ****************")
    device_data = db.get_device_status(conn)

    # Attach a generic display name for each device so frontends can show
    # human-friendly labels without duplicating string logic. This currently
    # applies neutral transforms (like "XXX on YYY" elision) that do not depend
    # on Hubitat being available.
    for dev in device_data:
        raw_name = dev.get("device_name", "")
        dev["display_name"] = display_device_name(raw_name, source="db")

    return jsonify({"devices": device_data})


@api_v1.route("/weather")
@with_db_connection
def get_weather(conn):
    """Get weather and AQI data"""
    weather_data = db.get_aqi_and_weather_data(conn)
    return jsonify(weather_data)


@api_v1.route("/temperature")
@with_db_connection
def get_temperature(conn):
    """Get temperature series data"""
    device_ids = parse_device_ids()
    if device_ids is None and request.args.get("device_ids"):
        return jsonify({"error": "Invalid device_ids format"}), 400
    series = db.get_temperature_series(conn, device_ids)
    # Use centralized helper for series display names, preferring Hubitat label when available
    # and applying display-only transforms.
    name_to_label = hubitat.get_name_to_label()
    for s in series:
        raw_name = s.get("name", "")
        hub_label = name_to_label.get(raw_name)
        s["name"] = display_device_name(
            raw_name,
            hubitat_label=hub_label,
            source="hubitat",
        )
    return jsonify({"series": series})


@api_v1.route("/air_quality")
@with_db_connection
def get_ai(conn):
    """Return aqi series data"""
    return jsonify(db.get_aqi_series(conn))


@api_v1.route("/lighting")
@with_db_connection
def get_lighting(conn):
    """Get lighting (illuminance) series data"""
    device_ids = parse_device_ids()
    if device_ids is None and request.args.get("device_ids"):
        return jsonify({"error": "Invalid device_ids format"}), 400
    series = db.get_lighting_series(conn, device_ids)
    # Use centralized helper for series display names, preferring Hubitat label
    # when available and applying display-only transforms.
    name_to_label = hubitat.get_name_to_label()
    for s in series:
        raw_name = s.get("name", "")
        hub_label = name_to_label.get(raw_name)
        s["name"] = display_device_name(
            raw_name,
            hubitat_label=hub_label,
            source="hubitat",
        )
    return jsonify({"series": series})


@api_v1.route("/metric")
@with_db_connection
def get_metric(conn):
    """Get per-device time series for a single air-quality metric."""
    metric = request.args.get("metric", "")
    status_key = db.AQ_METRIC_STATUS_KEYS.get(metric)
    if status_key is None:
        return jsonify({"error": f"Unknown metric: {metric!r}"}), 400
    device_ids = parse_device_ids()
    if device_ids is None and request.args.get("device_ids"):
        return jsonify({"error": "Invalid device_ids format"}), 400
    series = db.get_device_metric_series(conn, status_key, device_ids)
    name_to_label = hubitat.get_name_to_label()
    for s in series:
        raw_name = s.get("name", "")
        hub_label = name_to_label.get(raw_name)
        s["name"] = display_device_name(
            raw_name,
            hubitat_label=hub_label,
            source="airthings",
        )
    return jsonify({"series": series})


@api_v1.route("/logs")
@with_db_connection
def get_logs(conn):
    """Get changelog data"""
    logger.info("/logs")
    draw = request.args.get("draw", 1, type=int)
    start_row = request.args.get("start_row", 0, type=int)
    length = request.args.get("length", 100, type=int)

    result = db.get_changelog(conn, draw, start_row, length)
    return jsonify(result)


@api_v1.route("/disable-rules")
@with_db_connection
def disable_rules(conn):
    """Disable rules for a specified number of seconds"""
    seconds = request.args.get("seconds", type=int)
    logging.debug("/disable-rules seconds=%s", seconds)
    if seconds is None:
        return jsonify({"error": "seconds parameter is required"}), 400

    rules_engine.disable_all_rules(conn, seconds)
    return jsonify({"status": "success", "seconds": seconds})


@api_v1.route("/set_device_disabled_until", methods=["POST"])
@with_db_connection
def set_device_disabled_until(conn):
    """Set the per-device rules disable timer to an absolute epoch timestamp.

    Body: {"device_id": int, "disabled_until": int}
    A disabled_until <= now re-enables rules for the device (stored as 0).
    """
    payload = request.get_json(silent=True) or {}
    try:
        device_id = int(payload["device_id"])
        disabled_until = int(payload["disabled_until"])
    except (KeyError, ValueError, TypeError):
        return (
            jsonify({"error": "device_id and disabled_until (int) are required"}),
            400,
        )

    now = int(time.time())
    seconds = max(0, disabled_until - now)
    db.disable_rules_for_device(
        conn,
        device_id=device_id,
        seconds=seconds,
        ipaddr=request.remote_addr,
        agent=request.headers.get("User-Agent"),
        comment="set via Disable-for control",
    )
    return jsonify(
        {
            "status": "ok",
            "device_id": device_id,
            "disabled_until": (now + seconds) if seconds > 0 else 0,
        }
    )


@api_v1.route("/rules_master", methods=["GET", "POST"])
@with_db_connection
def rules_master(conn):
    """
    Get or set the global master rules switch state.

    - GET returns JSON: {"enabled": bool}
    - POST accepts JSON body {"enabled": bool} and updates the state.
    """
    if request.method == "GET":
        enabled = db.get_rules_master_enabled(conn)
        return jsonify({"enabled": enabled})

    # POST
    payload = request.get_json(silent=True) or {}

    if "enabled" not in payload:
        return jsonify({"error": "Missing 'enabled' field"}), 400

    enabled = bool(payload["enabled"])
    db.set_rules_master_enabled(conn, enabled)
    logger.info("Master rules switch set to enabled=%s", enabled)
    return jsonify({"enabled": enabled})


@api_v1.route("/alerts/active")
@with_db_connection
def alerts_active(conn):
    """Get all active alerts"""
    device_id = request.args.get("device_id", type=int)
    include_details = request.args.get("include_details", "false").lower() == "true"
    alerts = db_alerts.get_active_alerts(conn, device_id, include_details)
    return jsonify(alerts)


@api_v1.route("/alerts/history")
@with_db_connection
def alerts_history(conn):
    """Get alert history"""
    device_id = request.args.get("device_id", type=int)
    limit = request.args.get("limit", type=int, default=100)
    include_details = request.args.get("include_details", "false").lower() == "true"
    alerts = db_alerts.get_alert_history(conn, device_id, limit, include_details)
    return jsonify(alerts)


@api_v1.route("/update_note", methods=["POST"])
@validate()
@with_db_connection
def update_note(conn, body: NoteControl):
    """Update device notes"""
    logger.debug("/update_note: body=[%s]", body)
    notes = body.notes if body.notes else None
    device_id = db.update_device_notes(conn, body.device_id, notes)
    return jsonify({"status": "ok", "device_id": device_id})


@api_v1.route("/hickory/room_status")
def hickory_room_status():
    """Return current state of Hickory room control devices."""
    config = room_config.ROOM_CONFIGS.get("hickory", {})
    result = {}
    try:
        all_devices = hubitat.get_all_devices()
        by_id = {str(d.get("id")): d for d in all_devices}

        dimmer_id = config.get("dimmer_id")
        if dimmer_id and dimmer_id in by_id:
            attrs = by_id[dimmer_id].get("attributes", {})
            result["dimmer"] = {
                "level": int(attrs.get("level", 0)),
                "switch": attrs.get("switch", "off"),
            }
        for key in ("wall_inner_id", "wall_outer_id"):
            dev_id = config.get(key)
            if dev_id and dev_id in by_id:
                attrs = by_id[dev_id].get("attributes", {})
                result[key.replace("_id", "")] = {
                    "switch": attrs.get("switch", "off"),
                }
    except (RuntimeError, OSError) as e:
        logger.warning("Room status fetch failed: %s", e)
        return jsonify({"error": str(e)}), 500
    return jsonify(result)


@api_v1.route("/hickory/dimmer", methods=["POST"])
def hickory_dimmer():
    """Set the Hickory room light dimmer level (0-100)."""
    config = room_config.ROOM_CONFIGS.get("hickory", {})
    device_id = config.get("dimmer_id")
    if not device_id:
        return jsonify({"error": "No dimmer configured"}), 404
    payload = request.get_json(silent=True) or {}
    level = payload.get("level")
    if level is None or not isinstance(level, int) or not 0 <= level <= 100:
        return jsonify({"error": "level must be an integer 0-100"}), 400
    try:
        hubitat.set_dimmer_level(device_id, level)
        return jsonify({"status": "ok", "level": level})
    except (RuntimeError, OSError) as e:
        logger.warning("Dimmer control failed: %s", e)
        return jsonify({"error": str(e)}), 500


@api_v1.route("/hickory/wall_light", methods=["POST"])
def hickory_wall_light():
    """Toggle a Hickory wall light on or off."""
    config = room_config.ROOM_CONFIGS.get("hickory", {})
    payload = request.get_json(silent=True) or {}
    light = payload.get("light")
    state = payload.get("state")

    id_map = {"inner": config.get("wall_inner_id"), "outer": config.get("wall_outer_id")}
    if not isinstance(light, str):
        return jsonify({"error": "light must be 'inner' or 'outer'"}), 400
    device_id = id_map.get(light)
    if not device_id:
        return jsonify({"error": "light must be 'inner' or 'outer'"}), 400
    if not isinstance(state, str) or state not in ("on", "off"):
        return jsonify({"error": "state must be 'on' or 'off'"}), 400
    try:
        hubitat.set_switch(device_id, state)
        return jsonify({"status": "ok", "light": light, "state": state})
    except (RuntimeError, OSError) as e:
        logger.warning("Wall light control failed: %s", e)
        return jsonify({"error": str(e)}), 500


@api_v1.route("/hickory/tv", methods=["POST"])
def hickory_tv():
    """Control the Hickory TV lift (up/down)."""
    payload = request.get_json(silent=True) or {}
    direction = payload.get("direction")
    if direction not in ("up", "down"):
        return jsonify({"error": "direction must be 'up' or 'down'"}), 400
    try:
        hubitat.control_hickory_tv(direction)
        return jsonify({"status": "ok", "direction": direction})
    except (RuntimeError, OSError) as e:
        logger.warning("TV control failed: %s", e)
        return jsonify({"error": str(e)}), 500


@api_v1.route("/debug/db_devices")
@with_db_connection
def debug_db_devices(conn):
    """Get all devices from database for debug page"""
    try:
        device_data = db.get_device_status(conn)
        # Enrich names with Hubitat label in parens when available (same as Hubitat section)
        name_to_label = hubitat.get_name_to_label()
        device_names = []
        for dev in device_data:
            name = dev.get("device_name", "Unknown")
            if name in name_to_label:
                device_names.append(name + " (" + name_to_label[name] + ")")
            else:
                device_names.append(name)
        return jsonify({"names": device_names, "data": device_data})
    except (ValueError, RuntimeError, OSError) as e:
        logger.warning("Failed to fetch all devices: %s", e)
        return jsonify({"error": str(e)}), 500


@api_v1.route("/debug/hubitat_devices")
def debug_hubitat_devices():
    """Get all Hubitat devices for debug page"""
    try:
        hubitat_devices = hubitat.get_all_devices()
        device_names = [
            (dev.get("name", "Unknown") + " (" + dev.get("label", "") + ")")
            if dev.get("label")
            else dev.get("name", "Unknown")
            for dev in hubitat_devices
        ]
        return jsonify({"names": device_names, "data": hubitat_devices})
    except (ValueError, RuntimeError, OSError) as e:
        logger.warning("Failed to fetch Hubitat devices: %s", e)
        return jsonify({"error": str(e)}), 500


@api_v1.route("/debug/ae200_devices")
def debug_ae200_devices():
    """Get all AE-200 devices for debug page"""
    try:
        ae200_devices = ae200.get_devices()
        device_names = [dev.get("name", "Unknown") for dev in ae200_devices]

        # Per-device status direct from AE-200, fetched concurrently
        async def _fetch_ae200_details_async(devices):
            ae200_details: dict[str, dict[str, Any]] = {}
            tasks = []
            ids = []
            for dev in devices:
                device_id = dev.get("id")
                if device_id is None:
                    continue
                ids.append(str(device_id))
                tasks.append(ae200.get_device_info_async(device_id))
            if not tasks:
                return ae200_details
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for key, result in zip(ids, results):
                if isinstance(result, asyncio.CancelledError):
                    raise result
                if isinstance(result, Exception):
                    ae200_details[key] = {"error": str(result)}
                elif isinstance(result, BaseException):
                    raise result
                else:
                    ae200_details[key] = dict(result)
            return ae200_details

        ae200_details = ae200.runner.run_async_safely(
            _fetch_ae200_details_async(ae200_devices)
        )

        return jsonify(
            {"names": device_names, "devices": ae200_devices, "details": ae200_details}
        )
    except (ValueError, RuntimeError, OSError) as e:
        logger.warning("Failed to fetch AE-200 devices: %s", e)
        return jsonify({"error": str(e)}), 500
