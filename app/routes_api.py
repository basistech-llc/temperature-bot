"""
API route handlers
"""
import logging
from flask import Blueprint, request, jsonify
from flask_pydantic import validate

from .constants import __version__
from . import constants
from . import db
from . import rules_engine
from .utils.request_utils import parse_device_ids
from .utils.db_utils import with_db_connection

from .db import SpeedControl, DriveControl

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
    db.disable_rules_for_device(conn,
                                device_id = ret['device_id'],
                                seconds = constants.RULES_DISABLE_SECONDS,
                                ipaddr = request.remote_addr,
                                agent = request.headers.get('User-Agent'))
    return jsonify({"status": "ok", **ret})

@api_v1.route("/set_drive", methods=["POST"])
@validate()
@with_db_connection
def set_drive(conn, body: DriveControl):
    """Sets the speed, records the speed in the changelog, and then updates the database, so status is always up-to-date"""
    logger.debug("/set_drive: body=[%s]", body)
    ret = rules_engine.set_body_drive(conn, body, request.remote_addr, "web")
    device_id = ret['device_id']
    db.disable_rules_for_device(conn,
                                device_id = device_id,
                                seconds = constants.RULES_DISABLE_SECONDS,
                                ipaddr = request.remote_addr,
                                agent = request.headers.get('User-Agent'),
                                comment = f'rules for disabled for {constants.RULES_DISABLE_SECONDS/60} minutes')
    return jsonify({"status": "ok", **ret})

@api_v1.route("/status")
@with_db_connection
def get_status(conn):
    """Get device status"""
    logger.debug("**************** /status ****************")
    device_data = db.get_device_status(conn)
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
