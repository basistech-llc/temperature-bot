"""
API route handlers
"""

import logging
import sqlite3
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager

from flask import Blueprint, request, jsonify
from flask_pydantic import validate
from pydantic import TypeAdapter, ValidationError
from websockets.exceptions import WebSocketException

from . import constants
from .api_errors import (
    ApiError,
    BadRequest,
    Conflict,
    NotFound,
    UpstreamUnavailable,
    register_error_handlers,
)
from .version import __version__, git_sha
from . import db
from . import db_alerts
from . import rules_engine
from . import hubitat
from . import ae200
from .display_names import display_device_name
from . import room_config
from . import presence
from .device_types import HubitatControlDevice
from .utils.request_utils import parse_device_ids
from .utils.db_utils import with_db_connection

from .models import (
    ActiveAlert,
    AlertHistoryEntry,
    AutoSetTempControl,
    DeviceDisableUntilControl,
    DisableRulesQuery,
    CommandResponse,
    DeviceMetadataControl,
    DeviceRoomControl,
    FcuTempSourceBatchControl,
    DriveControl,
    FcuTempSourceControl,
    FcuHistoryResponse,
    ModeControl,
    NoteControl,
    SetRangeControl,
    Room,
    RoomCreate,
    RoomListResponse,
    RoomPatch,
    PresenceHistoryResponse,
    RoomPresenceResponse,
    RoomControlStatus,
    RoomDimmerControl,
    RoomDimmerState,
    RoomTvControl,
    RoomWallLightControl,
    RulesMasterControl,
    RoomSwitchState,
    SetTempControl,
    SpeedControl,
    TemperatureSeriesResponse,
    TimeSeriesResponse,
    alert_json_ready,
    json_ready,
)

logger = logging.getLogger(__name__)

# Create API blueprint
api_v1 = Blueprint("api_v1", __name__)
register_error_handlers(api_v1)
FCU_TEMP_SOURCE_BATCH_ADAPTER = TypeAdapter(FcuTempSourceBatchControl)

# Transport-level failures from the AE-200 WebSocket/Modbus adapter. These mean
# the hub could not be reached or answered unintelligibly, not that the request
# was wrong.
AE200_TRANSPORT_ERRORS = (ET.ParseError, OSError, RuntimeError, WebSocketException)


def _rules_disabled_comment() -> str:
    minutes = constants.RULES_DISABLE_SECONDS / 60
    return f"Rules disabled for {minutes:g} minutes"


def _run_ae200_command(command, conn, body):
    """Run one ``rules_engine`` command, mapping its failures to API errors.

    The client-facing messages are deliberately generic: raw exception text from
    this path can name devices and hub addresses, and tests assert that such
    text does not reach the response body.
    """
    try:
        return command(conn, body, request.remote_addr, "web")
    except ValueError as exc:
        if isinstance(exc, ApiError):
            # Conflict subclasses ValueError so that non-route callers catching
            # the builtin keep working. Re-raise it here rather than flattening
            # an already-classified 409 into a generic 400.
            raise
        logger.info("Command request rejected: %s", exc)
        raise BadRequest("Invalid command request") from exc
    except AE200_TRANSPORT_ERRORS as exc:  # pylint: disable=catching-non-exception
        logger.warning("AE-200 request failed: %s", exc)
        raise UpstreamUnavailable("AE-200 request failed") from exc


def _disable_rules_after_manual_command(conn, device_id: int) -> None:
    """Pause automation for a device an operator just commanded by hand."""
    db.disable_rules_for_device(
        conn,
        device_id=device_id,
        seconds=constants.RULES_DISABLE_SECONDS,
        ipaddr=request.remote_addr,
        agent=request.headers.get("User-Agent"),
        comment=_rules_disabled_comment(),
    )


def _command_response(ret: dict):
    """Serialize a successful command result."""
    return jsonify(json_ready(CommandResponse.model_validate({"status": "ok", **ret})))


@contextmanager
def _domain_errors():
    """Translate the remaining untyped database failures into API errors.

    ``db`` raises :class:`NotFound` and :class:`Conflict` directly for missing
    entities and state conflicts, and those pass straight through to the
    blueprint handler. What is left is genuine input validation (an unusable set
    range, a missing required field), which is a 400, plus SQLite uniqueness
    violations, which are a 409.

    ``Conflict`` subclasses ``ValueError`` so non-route callers catching the
    builtin keep working, which makes the ordering here load-bearing: catching
    ``ValueError`` without letting an ``ApiError`` through first would report an
    already-classified 409 as a generic 400.
    """
    try:
        yield
    except sqlite3.IntegrityError as e:
        raise Conflict(str(e)) from e
    except ValidationError as e:
        # A row we just read failed one of OUR OWN models: a server-side data
        # problem, not a caller mistake. Answer 500 with the detail in the log.
        # Merely re-raising is not enough -- the blueprint's client-validation
        # handler would turn it into a 400 that blames the caller and echoes
        # raw pydantic text. This arm must precede the ValueError one below,
        # because ValidationError subclasses ValueError.
        logger.exception("Database row failed model validation on %s", request.path)
        raise ApiError() from e
    except ValueError as e:
        if isinstance(e, ApiError):
            # Already classified further down; keep its status rather than
            # flattening a 409 Conflict into a generic 400.
            raise
        raise BadRequest(str(e)) from e


@contextmanager
def _hubitat_control(what: str):
    """Map Hubitat actuator failures to one upstream error.

    These previously answered 500 with the raw exception text. They are
    integration transport failures like the AE-200 ones, so they now answer 502
    with a generic message and log the detail instead.
    """
    try:
        yield
    except (RuntimeError, OSError) as e:
        logger.warning("%s control failed: %s", what, e)
        raise UpstreamUnavailable(f"{what} control failed") from e


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
    ret = _run_ae200_command(rules_engine.set_body_fan_speed, conn, body)
    _disable_rules_after_manual_command(conn, ret["device_id"])
    return _command_response(ret)


@api_v1.route("/set_drive", methods=["POST"])
@validate()
@with_db_connection
def set_drive(conn, body: DriveControl):
    """Sets the speed, records the speed in the changelog, and then updates the database, so status is always up-to-date"""
    logger.debug("/set_drive: body=[%s]", body)
    ret = _run_ae200_command(rules_engine.set_body_drive, conn, body)
    _disable_rules_after_manual_command(conn, ret["device_id"])
    return _command_response(ret)


@api_v1.route("/set_mode", methods=["POST"])
@validate()
@with_db_connection
def set_mode(conn, body: ModeControl):
    """Set an AE-200 operation mode and record the commanded state."""
    logger.debug("/set_mode: body=[%s]", body)
    ret = _run_ae200_command(rules_engine.set_body_mode, conn, body)
    _disable_rules_after_manual_command(conn, ret["device_id"])
    return _command_response(ret)


@api_v1.route("/set_temp", methods=["POST"])
@validate()
@with_db_connection
def set_temp(conn, body: SetTempControl):
    """Set the target temperature for a unit.

    The request body must provide `set_temp_c` in Celsius; the UI is responsible
    for converting from Fahrenheit if needed.
    """
    logger.debug("/set_temp: body=[%s]", body)
    return _command_response(
        _run_ae200_command(rules_engine.set_body_set_temp, conn, body)
    )


@api_v1.route("/set_auto_temp", methods=["POST"])
@validate()
@with_db_connection
def set_auto_temp(conn, body: AutoSetTempControl):
    """Set AE-200 Auto Heat/Cool setpoints for a unit."""
    logger.debug("/set_auto_temp: body=[%s]", body)
    return _command_response(
        _run_ae200_command(rules_engine.set_body_auto_set_temp, conn, body)
    )


@api_v1.route("/set_range", methods=["POST"])
@validate()
@with_db_connection
def set_range(conn, body: SetRangeControl):
    """Persist the FCU set range in Celsius."""
    # db raises NotFound for an unknown device; a plain ValueError here is a
    # range-validation failure.
    with _domain_errors():
        response = db.set_fcu_set_range(
            conn,
            device_id=body.device_id,
            set_range_low_c=body.set_range_low_c,
            set_range_high_c=body.set_range_high_c,
            ipaddr=request.remote_addr,
            agent=request.headers.get("User-Agent"),
        )
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
    body = DeviceMetadataControl.model_validate({**payload, "device_id": device_id})
    with _domain_errors():
        device = db.update_device_metadata(conn, body, fields=update_fields)
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
        raise BadRequest("Invalid device_ids format")
    if mode == "raw":
        series = db.get_temperature_series(conn, device_ids)
        boundary_device_ids = device_ids
    elif mode == "calculated":
        series, boundary_device_ids = db.get_calculated_temperature_series_and_device_ids(
            conn, device_ids
        )
    else:
        raise BadRequest("mode must be 'raw' or 'calculated'")
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


@api_v1.get("/fcu_history")
@with_db_connection
def get_fcu_history(conn):
    """Return time-aligned calculated room, inlet, mode, and fan history."""
    fcu_device_id = request.args.get("fcu_device_id", type=int)
    if fcu_device_id is None:
        raise BadRequest("fcu_device_id is required")
    history = db.get_fcu_history(conn, fcu_device_id)
    return jsonify(json_ready(FcuHistoryResponse.model_validate(history)))


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
        raise BadRequest("Invalid device_ids format")
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
    return jsonify(json_ready(TimeSeriesResponse.model_validate({"series": series})))


@api_v1.route("/metric")
@with_db_connection
def get_metric(conn):
    """Get per-device time series for a single air-quality metric."""
    metric = request.args.get("metric", "")
    status_key = db.AQ_METRIC_STATUS_KEYS.get(metric)
    if status_key is None:
        raise BadRequest(f"Unknown metric: {metric!r}")
    device_ids = parse_device_ids()
    if device_ids is None and request.args.get("device_ids"):
        raise BadRequest("Invalid device_ids format")
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
    return jsonify(json_ready(TimeSeriesResponse.model_validate({"series": series})))


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
@validate()
@with_db_connection
def disable_rules(conn, query: DisableRulesQuery):
    """Disable rules for a specified number of seconds"""
    seconds = query.seconds
    logging.debug("/disable-rules seconds=%s", seconds)
    rules_engine.disable_all_rules(
        conn,
        seconds,
        ipaddr=request.remote_addr,
        agent=request.headers.get("User-Agent"),
    )
    return jsonify({"status": "success", "seconds": seconds})


@api_v1.route("/set_device_disabled_until", methods=["POST"])
@validate()
@with_db_connection
def set_device_disabled_until(conn, body: DeviceDisableUntilControl):
    """Set the per-device rules disable timer to an absolute epoch timestamp.

    A ``disabled_until`` at or before now re-enables rules for the device
    (stored as 0).
    """
    device_id = body.device_id
    now = int(time.time())
    seconds = max(0, body.disabled_until - now)
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
        return jsonify(json_ready(RoomListResponse(rooms=db.get_rooms(conn))))

    body = RoomCreate.model_validate(request.get_json(silent=True) or {})
    with _domain_errors():
        room = db.create_room(conn, Room(room_name=body.room_name, map=body.map))
    return jsonify(json_ready(room)), 201


@api_v1.get("/rooms/<int:room_id>")
@with_db_connection
def room_detail(conn, room_id: int):
    """Return one room."""
    room = db.get_room(conn, room_id)
    if room is None:
        raise NotFound("room not found")
    return jsonify(json_ready(room))


@api_v1.get("/presence")
@with_db_connection
def room_presence(conn):
    """Return current presence for every canonical room."""
    return jsonify(
        json_ready(
            RoomPresenceResponse(
                stale_after_seconds=presence.PRESENCE_STALE_SECONDS,
                rooms=presence.get_room_presence(conn),
            )
        )
    )


@api_v1.get("/presence/history")
@with_db_connection
def room_presence_history(conn):
    """Return room-at-observation presence history."""
    room_id = request.args.get("room_id", type=int)
    since = request.args.get("since", type=int)
    if room_id is not None and db.get_room(conn, room_id) is None:
        raise NotFound("room not found")
    return jsonify(
        json_ready(
            PresenceHistoryResponse(
                events=db.get_presence_events(conn, room_id=room_id, since=since)
            )
        )
    )


@api_v1.patch("/rooms/<int:room_id>")
@with_db_connection
def update_room(conn, room_id: int):
    """Update one room."""
    body = RoomPatch.model_validate(request.get_json(silent=True) or {})
    update = Room(room_id=room_id)
    if "room_name" in body.model_fields_set:
        update.room_name = body.room_name
    if "map" in body.model_fields_set:
        update.map = body.map
    with _domain_errors():
        room = db.update_room(conn, update)
    if room is None:
        raise NotFound("room not found")
    return jsonify(json_ready(room))


@api_v1.delete("/rooms/<int:room_id>")
@with_db_connection
def delete_room(conn, room_id: int):
    """Delete a room only when it has no FCU owner or assigned devices."""
    with _domain_errors():
        deleted = db.delete_empty_room(conn, room_id)
    if not deleted:
        raise NotFound("room not found")
    return "", 204


@api_v1.route("/update_device_room", methods=["POST"])
@validate()
@with_db_connection
def update_device_room(conn, body: DeviceRoomControl):
    """Assign a device to a room, or clear the assignment with room_id=null."""
    with _domain_errors():
        device_id = db.update_device_room(conn, body.device_id, body.room_id)
    return jsonify(json_ready(CommandResponse(device_id=device_id)))


@api_v1.route("/fcu_temp_sources")
@with_db_connection
def get_fcu_temp_sources(conn):
    """Return all temperature-reporting source candidates for one FCU."""
    fcu_device_id = request.args.get("fcu_device_id", type=int)
    if fcu_device_id is None:
        raise BadRequest("fcu_device_id is required")
    return jsonify(db.get_fcu_temp_sources(conn, fcu_device_id))


@api_v1.route("/fcu_temp_source", methods=["POST"])
@with_db_connection
def set_fcu_temp_source(conn):
    """Persist one or more FCU temperature-source multipliers atomically."""
    payload = request.get_json(silent=True)
    if isinstance(payload, list):
        updates = FCU_TEMP_SOURCE_BATCH_ADAPTER.validate_python(payload)
    else:
        updates = [FcuTempSourceControl.model_validate(payload or {})]

    fcu_device_ids = {update.fcu_device_id for update in updates}
    if len(fcu_device_ids) > 1:
        raise BadRequest("all updates must use the same fcu_device_id")

    with _domain_errors():
        response = db.set_fcu_temp_source_multipliers(
            conn,
            updates=updates,
            ipaddr=request.remote_addr,
            agent=request.headers.get("User-Agent"),
        )
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

    # POST. Validated by hand rather than with @validate() because the same
    # view serves GET, which has no body to validate.
    body = RulesMasterControl.model_validate(request.get_json(silent=True) or {})
    enabled = body.enabled
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
    return jsonify(
        [alert_json_ready(ActiveAlert.model_validate(alert)) for alert in alerts]
    )


@api_v1.route("/alerts/history")
@with_db_connection
def alerts_history(conn):
    """Get alert history"""
    device_id = request.args.get("device_id", type=int)
    limit = request.args.get("limit", type=int, default=100)
    include_details = request.args.get("include_details", "false").lower() == "true"
    alerts = db_alerts.get_alert_history(conn, device_id, limit, include_details)
    return jsonify(
        [alert_json_ready(AlertHistoryEntry.model_validate(alert)) for alert in alerts]
    )


@api_v1.route("/update_note", methods=["POST"])
@validate()
@with_db_connection
def update_note(conn, body: NoteControl):
    """Update device notes"""
    logger.debug("/update_note: body=[%s]", body)
    notes = body.notes if body.notes else None
    device_id = db.update_device_notes(conn, body.device_id, notes)
    return jsonify(json_ready(CommandResponse(device_id=device_id)))


def _require_room_config(room_key: str):
    """Return the dashboard configuration for a room key, or raise 404."""
    config = room_config.find_room_config(room_key.casefold())
    if config is None:
        raise NotFound("Unknown room control configuration")
    return config


@api_v1.route("/hickory/room_status", defaults={"room_key": "hickory"})
@api_v1.route("/room/<room_key>/room_status")
def room_control_status(room_key: str):
    """Return current state of one configured room's control devices."""
    config = _require_room_config(room_key)
    result = RoomControlStatus()

    def read_device(device_id: str | None) -> HubitatControlDevice | None:
        if device_id is None:
            return None
        try:
            return HubitatControlDevice.model_validate(hubitat.get_device_info(device_id))
        except (RuntimeError, OSError, ValueError) as e:
            logger.warning("Room device %s status fetch failed: %s", device_id, e)
            return None

    if dimmer := read_device(config.dimmer_id):
        result.dimmer = RoomDimmerState(
            level=dimmer.attributes.level or 0,
            switch=dimmer.attributes.switch or "off",
        )
    if wall_inner := read_device(config.wall_inner_id):
        result.wall_inner = RoomSwitchState(
            switch=wall_inner.attributes.switch or "off"
        )
    if wall_outer := read_device(config.wall_outer_id):
        result.wall_outer = RoomSwitchState(
            switch=wall_outer.attributes.switch or "off"
        )
    return jsonify(json_ready(result))


@api_v1.route("/hickory/dimmer", methods=["POST"], defaults={"room_key": "hickory"})
@api_v1.route("/room/<room_key>/dimmer", methods=["POST"])
@validate()
def room_dimmer(room_key: str, body: RoomDimmerControl):
    """Set a configured room's light dimmer level (0-100)."""
    config = _require_room_config(room_key)
    device_id = config.dimmer_id
    if not device_id:
        raise NotFound("No dimmer configured")
    with _hubitat_control("Dimmer"):
        hubitat.set_dimmer_level(device_id, body.level)
    return jsonify(json_ready(CommandResponse(level=body.level)))


@api_v1.route("/hickory/wall_light", methods=["POST"], defaults={"room_key": "hickory"})
@api_v1.route("/room/<room_key>/wall_light", methods=["POST"])
@validate()
def room_wall_light(room_key: str, body: RoomWallLightControl):
    """Toggle a configured room's wall light on or off."""
    config = _require_room_config(room_key)
    id_map = {"inner": config.wall_inner_id, "outer": config.wall_outer_id}
    device_id = id_map.get(body.light)
    if not device_id:
        # The name is valid but this room has no such light configured.
        raise NotFound(f"No {body.light} wall light configured")
    with _hubitat_control("Wall light"):
        hubitat.set_switch(device_id, body.state)
    return jsonify(json_ready(CommandResponse(light=body.light, state=body.state)))


@api_v1.route("/hickory/tv", methods=["POST"], defaults={"room_key": "hickory"})
@api_v1.route("/room/<room_key>/tv", methods=["POST"])
@validate()
def room_tv(room_key: str, body: RoomTvControl):
    """Control a configured room's TV lift (up/down)."""
    config = _require_room_config(room_key)
    if not config.tv_up_label or not config.tv_down_label:
        raise NotFound("No TV configured")
    with _hubitat_control("TV"):
        hubitat.control_room_tv(
            body.direction,
            up_label=config.tv_up_label,
            down_label=config.tv_down_label,
        )
    return jsonify(json_ready(CommandResponse(direction=body.direction)))


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
        raise UpstreamUnavailable("Device lookup failed") from e


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
        raise UpstreamUnavailable("Hubitat request failed") from e


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
        logger.info("Command request rejected: %s", e)
        raise BadRequest("Invalid command request") from e
    except AE200_TRANSPORT_ERRORS as e:  # pylint: disable=catching-non-exception
        logger.warning("AE-200 request failed: %s", e)
        raise UpstreamUnavailable("AE-200 request failed") from e
