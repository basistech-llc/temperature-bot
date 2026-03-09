"""
API route handlers
"""

import asyncio
import logging
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
from .utils.request_utils import parse_device_ids
from .utils.db_utils import with_db_connection

from .db import SpeedControl, DriveControl, NoteControl, SetTempControl

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


@api_v1.route("/air_quality")
@with_db_connection
def get_ai(conn):
    """Return aqi series data"""
    return jsonify(db.get_aqi_series(conn))


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
            ae200_details = {}
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
                if isinstance(result, Exception):
                    ae200_details[key] = {"error": str(result)}
                else:
                    ae200_details[key] = result
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
