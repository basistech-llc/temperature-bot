"""
API route handlers
"""
import logging
from flask import Blueprint, request, jsonify
from flask_pydantic import validate

from .. import db
from ..services.device_service import DeviceService
from ..services.weather_service import WeatherService
from .common import LogService, with_db_connection, parse_device_ids, rules_engine, __version__

logger = logging.getLogger(__name__)

# Create API blueprint
api_v1 = Blueprint("api_v1", __name__)

# Initialize services
device_service = DeviceService()
weather_service = WeatherService()
log_service = LogService()


@api_v1.route("/version")
def get_version_json():
    return jsonify({"version": __version__})


@api_v1.route("/set_fan_speed", methods=["POST"])
@validate()
@with_db_connection
def set_fan_speed(conn, body: db.SpeedControl):
    """Sets the speed, records the speed in the changelog, and then updates the database, so status is always up-to-date"""
    logger.debug("/set_fan_speed: body=[%s]", body)
    ret = rules_engine.set_body_fan_speed(conn, body, request.remote_addr, "web")
    logging.debug("ret=%s", ret)
    return jsonify({"status": "ok", **ret})


@api_v1.route("/set_drive", methods=["POST"])
@validate()
@with_db_connection
def set_drive(conn, body: db.DriveControl):
    """Sets the speed, records the speed in the changelog, and then updates the database, so status is always up-to-date"""
    logger.debug("/set_drive: body=[%s]", body)
    ret = rules_engine.set_body_drive(conn, body, request.remote_addr, "web")
    logging.debug("ret=%s", ret)
    return jsonify({"status": "ok", **ret})


@api_v1.route("/status")
@with_db_connection
def get_status(conn):
    """Get device status"""
    logger.debug("**************** /status ****************")
    device_data = device_service.get_device_status(conn)
    return jsonify({"devices": device_data})


@api_v1.route("/weather")
@with_db_connection
def get_weather(conn):
    """Get weather and AQI data"""
    weather_data = weather_service.get_weather_data(conn)
    return jsonify(weather_data)


@api_v1.route("/temperature")
@with_db_connection
def get_temperature_series(conn):
    """Get temperature series data"""
    device_ids = parse_device_ids()
    if device_ids is None and request.args.get("device_ids"):
        return jsonify({"error": "Invalid device_ids format"}), 400

    series = device_service.get_temperature_series(conn, device_ids)
    return jsonify({"series": series})


@api_v1.route("/logs")
@with_db_connection
def get_logs(conn):
    """Get changelog data"""
    logger.info("/logs")
    draw = request.args.get("draw", 1, type=int)
    start_row = request.args.get("start_row", 0, type=int)
    length = request.args.get("length", 100, type=int)

    result = log_service.get_changelog(conn, draw, start_row, length)
    return jsonify(result)


@api_v1.route("/disable-rules")
@with_db_connection
def disable_rules(conn):
    """Disable rules for a specified number of seconds.
    :param seconds: - number of seconds to disable rules. 0 enables rules
    :param device_id: - just disable for this device
    """
    seconds = request.args.get("seconds", type=int)
    device_id = request.args.get("device_id", 0, type=int)
    logging.debug("/disable-rules seconds=%s device_id=%s", seconds, device_id)
    if seconds is None:
        return jsonify({"error": "seconds parameter is required"}), 400

    db.disable_rules(conn, device_id=device_id, seconds=seconds)
    return jsonify({"status": "success", "seconds": seconds})
