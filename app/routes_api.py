"""
API route handlers
"""

import logging
import sqlite3
import time
import xml.etree.ElementTree as ET

from flask import Blueprint, request, jsonify
from flask_pydantic import validate
from pydantic import TypeAdapter, ValidationError
from websockets.exceptions import WebSocketException

from . import constants
from .version import __version__, git_sha
from . import db
from . import db_alerts
from . import rules_engine
from . import hubitat
from . import ae200
from .display_names import display_device_name
from . import room_config
from .utils.request_utils import parse_device_ids
from .utils.db_utils import with_db_connection

from .models import (
    AutoSetTempControl,
    CommandResponse,
    DeviceMetadataControl,
    DeviceRoomControl,
    FcuTempSourceBatchControl,
    DriveControl,
    FcuTempSourceControl,
    ModeControl,
    NoteControl,
    SetRangeControl,
    Room,
    SetTempControl,
    SpeedControl,
    TemperatureSeriesResponse,
    json_ready,
    json_ready_list,
)

logger = logging.getLogger(__name__)

# Create API blueprint
api_v1 = Blueprint("api_v1", __name__)
FCU_TEMP_SOURCE_BATCH_ADAPTER = TypeAdapter(FcuTempSourceBatchControl)


def _validation_error_response(error: ValidationError):
    return jsonify({"error": "validation error", "details": error.errors()}), 400


def _rules_disabled_comment() -> str:
    minutes = constants.RULES_DISABLE_SECONDS / 60
    return f"Rules disabled for {minutes:g} minutes"


def _command_error_response(error: ValueError):
    logger.info("Command request rejected: %s", error)
    return jsonify({"error": str(error)}), 400


def _ae200_error_response(error):
    logger.warning("AE-200 request failed: %s", error)
    return jsonify({"error": f"AE-200 request failed: {error}"}), 502


@api_v1.route("/version")
def get_version_json():
    return jsonify({"version": __version__, "sha": git_sha()})


@api_v1.route("/set_fan_speed", methods=["POST"])
@validate()
@with_db_connection
def set_fan_speed(conn, body: SpeedControl):
    """Sets the speed, records the speed in the changelog,
    and then updates the database, so status is always up-to-date"""
    logger.debug("/set_fan_speed: body=[%s]", body)
    try:
        ret = rules_engine.set_body_fan_speed(conn, body, request.remote_addr, "web")
    except ValueError as exc:
        return _command_error_response(exc)
    except (ET.ParseError, OSError, RuntimeError, WebSocketException) as exc:
        return _ae200_error_response(exc)
    db.disable_rules_for_device(
        conn,
        device_id=ret["device_id"],
        seconds=constants.RULES_DISABLE_SECONDS,
        ipaddr=request.remote_addr,
        agent=request.headers.get("User-Agent"),
    )
    return jsonify(json_ready(CommandResponse.model_validate({"status": "ok", **ret})))


@api_v1.route("/set_drive", methods=["POST"])
@validate()
@with_db_connection
def set_drive(conn, body: DriveControl):
    """Sets the speed, records the speed in the changelog, and then updates the database, so status is always up-to-date"""
    logger.debug("/set_drive: body=[%s]", body)
    try:
        ret = rules_engine.set_body_drive(conn, body, request.remote_addr, "web")
    except ValueError as exc:
        return _command_error_response(exc)
    except (ET.ParseError, OSError, RuntimeError, WebSocketException) as exc:
        return _ae200_error_response(exc)
    device_id = ret["device_id"]
    db.disable_rules_for_device(
        conn,
        device_id=device_id,
        seconds=constants.RULES_DISABLE_SECONDS,
        ipaddr=request.remote_addr,
        agent=request.headers.get("User-Agent"),
        comment=_rules_disabled_comment(),
    )
    return jsonify(json_ready(CommandResponse.model_validate({"status": "ok", **ret})))


@api_v1.route("/set_mode", methods=["POST"])
@validate()
@with_db_connection
def set_mode(conn, body: ModeControl):
    """Set an AE-200 operation mode and record the commanded state."""
    logger.debug("/set_mode: body=[%s]", body)
    try:
        ret = rules_engine.set_body_mode(conn, body, request.remote_addr, "web")
    except ValueError as exc:
        return _command_error_response(exc)
    except (ET.ParseError, OSError, RuntimeError, WebSocketException) as exc:
        return _ae200_error_response(exc)
    db.disable_rules_for_device(
        conn,
        device_id=ret["device_id"],
        seconds=constants.RULES_DISABLE_SECONDS,
        ipaddr=request.remote_addr,
        agent=request.headers.get("User-Agent"),
        comment=_rules_disabled_comment(),
    )
    return jsonify(json_ready(CommandResponse.model_validate({"status": "ok", **ret})))


@api_v1.route("/set_temp", methods=["POST"])
@validate()
@with_db_connection
def set_temp(conn, body: SetTempControl):
    """Set the target temperature for a unit.

    The request body must provide `set_temp_c` in Celsius; the UI is responsible
    for converting from Fahrenheit if needed.
    """
    logger.debug("/set_temp: body=[%s]", body)
    try:
        ret = rules_engine.set_body_set_temp(conn, body, request.remote_addr, "web")
    except ValueError as exc:
        return _command_error_response(exc)
    except (ET.ParseError, OSError, RuntimeError, WebSocketException) as exc:
        return _ae200_error_response(exc)
    return jsonify(json_ready(CommandResponse.model_validate({"status": "ok", **ret})))


@api_v1.route("/set_auto_temp", methods=["POST"])
@validate()
@with_db_connection
def set_auto_temp(conn, body: AutoSetTempControl):
    """Set AE-200 Auto Heat/Cool setpoints for a unit."""
    logger.debug("/set_auto_temp: body=[%s]", body)
    try:
        ret = rules_engine.set_body_auto_set_temp(
            conn,
            body,
            request.remote_addr,
            "web",
        )
    except ValueError as exc:
        return _command_error_response(exc)
    except (ET.ParseError, OSError, RuntimeError, WebSocketException) as exc:
        return _ae200_error_response(exc)
    return jsonify(json_ready(CommandResponse.model_validate({"status": "ok", **ret})))


@api_v1.route("/set_range", methods=["POST"])
@validate()
@with_db_connection
def set_range(conn, body: SetRangeControl):
    """Persist the FCU set range in Celsius."""
    try:
        response = db.set_fcu_set_range(
            conn,
            device_id=body.device_id,
            set_range_low_c=body.set_range_low_c,
            set_range_high_c=body.set_range_high_c,
            ipaddr=request.remote_addr,
            agent=request.headers.get("User-Agent"),
        )
    except ValueError as e:
        status_code = 404 if str(e).startswith("Unknown") else 400
        return jsonify({"error": str(e)}), status_code
    return jsonify(response)


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
        dev["display_name"] = dev.get("display_name") or display_device_name(
            raw_name, source="db"
        )

    return jsonify({"devices": device_data})


@api_v1.route("/devices", methods=["GET"])
@with_db_connection
def devices(conn):
    """Return editable device catalog rows."""
    return jsonify({"devices": db.get_device_metadata(conn)})


@api_v1.patch("/devices/<int:device_id>")
@with_db_connection
def update_device(conn, device_id: int):
    """Update editable device metadata."""
    payload = request.get_json(silent=True) or {}
    allowed_fields = {"display_name", "device_type", "rules_enabled", "notes"}
    update_fields = allowed_fields.intersection(payload)
    try:
        body = DeviceMetadataControl.model_validate(
            {**payload, "device_id": device_id}
        )
        device = db.update_device_metadata(conn, body, fields=update_fields)
    except ValidationError as e:
        return _validation_error_response(e)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify(device)


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
    mode = request.args.get("mode", "raw")
    device_ids = parse_device_ids()
    if device_ids is None and request.args.get("device_ids"):
        return jsonify({"error": "Invalid device_ids format"}), 400
    if mode == "raw":
        series = db.get_temperature_series(conn, device_ids)
        boundary_device_ids = device_ids
    elif mode == "calculated":
        series = db.get_calculated_temperature_series(conn, device_ids)
        boundary_device_ids = db.get_calculated_temperature_device_ids(
            conn, device_ids
        )
    else:
        return jsonify({"error": "mode must be 'raw' or 'calculated'"}), 400
    has_earlier_data, has_later_data = db.temperature_data_availability(
        conn,
        boundary_device_ids,
        request.args.get("start", type=int),
        request.args.get("end", type=int),
    )
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
    return jsonify(
        json_ready(
            TemperatureSeriesResponse.model_validate(
                {
                    "series": series,
                    "has_earlier_data": has_earlier_data,
                    "has_later_data": has_later_data,
                }
            )
        )
    )


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


@api_v1.route("/rooms", methods=["GET", "POST"])
@with_db_connection
def rooms(conn):
    """List or create rooms with map polygon metadata."""
    if request.method == "GET":
        return jsonify({"rooms": json_ready_list(db.get_rooms(conn))})

    try:
        body = Room.model_validate(request.get_json(silent=True) or {})
        room = db.create_room(conn, body)
    except ValidationError as e:
        return _validation_error_response(e)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except sqlite3.IntegrityError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify(json_ready(room)), 201


@api_v1.get("/rooms/<int:room_id>")
@with_db_connection
def room_detail(conn, room_id: int):
    """Return one room."""
    room = db.get_room(conn, room_id)
    if room is None:
        return jsonify({"error": "room not found"}), 404
    return jsonify(json_ready(room))


@api_v1.patch("/rooms/<int:room_id>")
@with_db_connection
def update_room(conn, room_id: int):
    """Update one room."""
    try:
        body = Room.model_validate(
            {**(request.get_json(silent=True) or {}), "room_id": room_id}
        )
        room = db.update_room(conn, body)
    except ValidationError as e:
        return _validation_error_response(e)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except sqlite3.IntegrityError as e:
        return jsonify({"error": str(e)}), 409
    if room is None:
        return jsonify({"error": "room not found"}), 404
    return jsonify(json_ready(room))


@api_v1.route("/update_device_room", methods=["POST"])
@validate()
@with_db_connection
def update_device_room(conn, body: DeviceRoomControl):
    """Assign a device to a room, or clear the assignment with room_id=null."""
    try:
        device_id = db.update_device_room(conn, body.device_id, body.room_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify(json_ready(CommandResponse(device_id=device_id)))


@api_v1.route("/fcu_temp_sources")
@with_db_connection
def get_fcu_temp_sources(conn):
    """Return all temperature-reporting source candidates for one FCU."""
    fcu_device_id = request.args.get("fcu_device_id", type=int)
    if fcu_device_id is None:
        return jsonify({"error": "fcu_device_id is required"}), 400
    try:
        return jsonify(db.get_fcu_temp_sources(conn, fcu_device_id))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@api_v1.route("/fcu_temp_source", methods=["POST"])
@with_db_connection
def set_fcu_temp_source(conn):
    """Persist one or more FCU temperature-source multipliers atomically."""
    payload = request.get_json(silent=True)
    try:
        if isinstance(payload, list):
            updates = FCU_TEMP_SOURCE_BATCH_ADAPTER.validate_python(payload)
        else:
            updates = [FcuTempSourceControl.model_validate(payload or {})]
    except ValidationError as e:
        return _validation_error_response(e)

    fcu_device_ids = {update.fcu_device_id for update in updates}
    if len(fcu_device_ids) > 1:
        return jsonify({"error": "all updates must use the same fcu_device_id"}), 400

    try:
        response = db.set_fcu_temp_source_multipliers(
            conn,
            updates=updates,
            ipaddr=request.remote_addr,
            agent=request.headers.get("User-Agent"),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify(response)


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
    return jsonify(json_ready(CommandResponse(device_id=device_id)))


@api_v1.route("/hickory/room_status")
def hickory_room_status():
    """Return current state of Hickory room control devices."""
    config = room_config.get_room_config("hickory")
    result = {}
    try:
        all_devices = hubitat.get_all_devices()
        by_id = {str(d.get("id")): d for d in all_devices}

        dimmer_id = config.dimmer_id
        if dimmer_id and dimmer_id in by_id:
            attrs = by_id[dimmer_id].get("attributes", {})
            result["dimmer"] = {
                "level": int(attrs.get("level", 0)),
                "switch": attrs.get("switch", "off"),
            }
        for key, dev_id in {
            "wall_inner_id": config.wall_inner_id,
            "wall_outer_id": config.wall_outer_id,
        }.items():
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
    config = room_config.get_room_config("hickory")
    device_id = config.dimmer_id
    if not device_id:
        return jsonify({"error": "No dimmer configured"}), 404
    payload = request.get_json(silent=True) or {}
    level = payload.get("level")
    if level is None or not isinstance(level, int) or not 0 <= level <= 100:
        return jsonify({"error": "level must be an integer 0-100"}), 400
    try:
        hubitat.set_dimmer_level(device_id, level)
        return jsonify(json_ready(CommandResponse(level=level)))
    except (RuntimeError, OSError) as e:
        logger.warning("Dimmer control failed: %s", e)
        return jsonify({"error": str(e)}), 500


@api_v1.route("/hickory/wall_light", methods=["POST"])
def hickory_wall_light():
    """Toggle a Hickory wall light on or off."""
    config = room_config.get_room_config("hickory")
    payload = request.get_json(silent=True) or {}
    light = payload.get("light")
    state = payload.get("state")

    id_map = {"inner": config.wall_inner_id, "outer": config.wall_outer_id}
    if not isinstance(light, str):
        return jsonify({"error": "light must be 'inner' or 'outer'"}), 400
    device_id = id_map.get(light)
    if not device_id:
        return jsonify({"error": "light must be 'inner' or 'outer'"}), 400
    if not isinstance(state, str) or state not in ("on", "off"):
        return jsonify({"error": "state must be 'on' or 'off'"}), 400
    try:
        hubitat.set_switch(device_id, state)
        return jsonify(json_ready(CommandResponse(light=light, state=state)))
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
        return jsonify(json_ready(CommandResponse(direction=direction)))
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

        ae200_details = {}
        for dev in ae200_devices:
            device_id = dev.get("id")
            if device_id is None:
                continue
            try:
                ae200_details[str(device_id)] = dict(ae200.get_device_info(device_id))
            except (
                ET.ParseError,
                OSError,
                RuntimeError,
                ValueError,
                WebSocketException,
            ) as e:
                ae200_details[str(device_id)] = {"error": str(e)}

        return jsonify(
            {"names": device_names, "devices": ae200_devices, "details": ae200_details}
        )
    except ValueError as e:
        return _command_error_response(e)
    except (ET.ParseError, OSError, RuntimeError, WebSocketException) as e:
        return _ae200_error_response(e)
