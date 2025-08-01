"""
app.py - Flask version
"""

from os.path import abspath
import os
import logging
import json
import datetime
import time
from typing import Any
from functools import wraps

from flask import Flask, Blueprint, request, jsonify, render_template, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix


from flask_pydantic import validate


from . import ae200
from . import weather
from . import db
from . import airquality
from . import rules_engine
from .db import SpeedControl

__version__ = "0.0.1"

DEV = "/home/simsong" in abspath(__file__)
API_V1_PREFIX = "/api/v1"
DEFAULT_LOG_LEVEL = "DEBUG"
LOGGING_CONFIG = "%(asctime)s  %(filename)s:%(lineno)d %(levelname)s: %(message)s"
LOG_LEVEL = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
LOG_LEVEL = "DEBUG"

# logging.basicConfig(
#    format=LOGGING_CONFIG,
#    level=LOG_LEVEL,
#    force=True,
#    stream=sys.stderr  # Ensure logs go to stderr for gunicorn
# )
# logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)

# logger.debug("HELP")


def fix_boto_log_level():
    """Do not run boto loggers at debug level"""
    for name in logging.root.manager.loggerDict:  # pylint: disable=no-member
        if name.startswith("boto"):
            logging.getLogger(name).setLevel(logging.INFO)


# https://flask.palletsprojects.com/en/stable/config/
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
app.config["TEMPLATES_AUTO_RELOAD"] = True
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logger = app.logger
logging.basicConfig(format=LOGGING_CONFIG, level=log_level, force=True)
logger.setLevel(log_level)
app.logger.info("new Flask(__name__=%s) log_level=%s", __name__, log_level)
fix_boto_log_level()

# Initialize logging and boto settings
# fix_boto_log_level()

################################################################

# System map dictionary
SYSTEM_MAP = {12: "Kitchen ERV", 13: "Bathroom ERV"}


def get_db_connection():
    """Get database connection for current request"""
    return db.get_db_connection()


def with_db_connection(f):
    """Decorator to handle database connections properly"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        conn = get_db_connection()
        try:
            return f(conn, *args, **kwargs)
        finally:
            conn.close()

    return decorated_function


def get_db_aqi(conn):
    """
    Get AQI from database.

    :param conn: database connection
    :return: AQI data dict with value, color, name
    """

    # Check for recent AQI data in database
    c = conn.cursor()
    c.execute("SELECT aqi FROM aqi order by logtime DESC limit 1")
    row = c.fetchone()
    aqi = row[0] if row is not None else 0
    return airquality.aqi_decode(aqi)


def get_last_db_data(conn):
    def fix_status_json(devdict):
        devdict = dict(devdict)
        try:
            devdict["status"] = json.loads(devdict["status_json"])
        except (TypeError, json.JSONDecodeError):
            pass
        del devdict["status_json"]
        return devdict

    return [fix_status_json(dd) for dd in db.fetch_last_status(conn)]


################################################################
### Query support


def github_style_duration(past_time, now=None):
    if now is None:
        now = time.time()
    seconds = int(now - past_time)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    if days < 30:
        return f"{days}d"
    months = days // 30
    if months < 12:
        return f"{months}mo"
    years = months // 12
    return f"{years}y"


def temporal_quantification(cmd, args):
    """Anotate cmd and args with start, end, limit"""
    start = request.args.get("start", type=int)
    end = request.args.get("end", type=int)

    if start is not None:
        cmd += " AND logtime >= ? "
        args.append(start)

    if end is not None:
        cmd += " AND logtime <= ? "
        args.append(end)

    return (cmd, args)


################################################################
# Versioned API routes

api_v1 = Blueprint("api_v1", __name__)


@api_v1.route("/version")
def get_version_json():
    return jsonify({"version": __version__})


@api_v1.route("/set_speed", methods=["POST"])
@validate()
@with_db_connection
def set_speed(conn, body: SpeedControl):
    """Sets the speed, records the speed in the changelog, and then updates the database, so status is always up-to-date"""
    logger.debug("/set_speed: body=[%s]", body)
    ret = rules_engine.set_body_speed(conn, body, request.remote_addr, "web")
    logging.debug("ret=%s", ret)
    return jsonify({"status": "ok", **ret})


@api_v1.route("/status")
@with_db_connection
def get_status(conn):
    device_data = get_last_db_data(conn)

    # Annotate the device_data
    for data in device_data:
        if "status" in data:
            data.update(ae200.extract_status(data["status"]))
        if "logtime" in data:
            data["age"] = github_style_duration(
                data["logtime"] + data.get("duration", 1)
            )

    return jsonify({"devices": device_data})


@api_v1.route("/weather")
@with_db_connection
def get_weather(conn):
    aqi_data = get_db_aqi(conn)
    weather_data = weather.get_weather_data()
    return jsonify({"aqi": aqi_data, "weather": weather_data})


# Removed /api/v1/devices endpoint; use /api/v1/status for device info


@api_v1.route("/temperature")
@with_db_connection
def get_temperature_series(conn):
    device_ids_param = request.args.get("device_ids", "")

    c = conn.cursor()
    series = []

    if device_ids_param:
        # Parse device_ids - can be single value or comma-separated list
        try:
            device_ids = [
                int(did.strip()) for did in device_ids_param.split(",") if did.strip()
            ]
        except ValueError:
            return jsonify({"error": "Invalid device_ids format"}), 400

        # Get specific devices
        for device_id in device_ids:
            c.execute("SELECT * from devices where device_id=?", (device_id,))
            device = c.fetchone()
            if device:
                cmd = """
                    SELECT logtime,temp10x from devlog
                    where device_id=? and logtime is not null and temp10x is not null
                """
                args = [device_id]
                (cmd, args) = temporal_quantification(cmd, args)
                cmd += " order by logtime"

                c.execute(cmd, args)
                rows = c.fetchall()
                data = [[row["logtime"], row["temp10x"] / 10] for row in rows]
                if data:
                    series.append({"name": device["device_name"], "data": data})
    else:
        # Get all devices
        c.execute("SELECT * from devices")
        devices = c.fetchall()
        for dev in devices:
            cmd = """
                SELECT logtime,temp10x from devlog
                where device_id=? and logtime is not null and temp10x is not null
            """
            args = [dev["device_id"]]
            (cmd, args) = temporal_quantification(cmd, args)
            cmd += " order by logtime"

            c.execute(cmd, args)
            rows = c.fetchall()
            data = [[row["logtime"], row["temp10x"] / 10] for row in rows]
            if data:
                series.append({"name": dev["device_name"], "data": data})

    return jsonify({"series": series})


@api_v1.route("/logs")
@with_db_connection
def get_logs(conn):
    logger.info("/logs")
    draw = request.args.get("draw", 1, type=int)
    start_row = request.args.get("start_row", 0, type=int)
    length = request.args.get("length", 100, type=int)

    cmd = """SELECT c.logtime, c.ipaddr, d.device_name as unit, c.new_value, c.agent, c.comment FROM changelog c
               LEFT JOIN devices d ON c.device_id = d.device_id WHERE 1=1"""
    args: list[Any] = []

    (cmd, args) = temporal_quantification(cmd, args)

    cmd += " ORDER BY logtime DESC LIMIT ? OFFSET ?"
    args.extend([length, start_row])
    logger.debug("cmd=%s args=%s", cmd, args)

    c = conn.cursor()
    c.execute(cmd, args)
    rows = [
        dict(row) for row in c.fetchall()
    ]  # Convert Row objects to dicts for JSON serialization
    for row in rows:
        try:
            row["age"] = github_style_duration(row["logtime"])
        except TypeError as e:
            logging.error("e=%s data=%s", e, row)

    return jsonify(
        {
            "draw": draw,
            "recordsTotal": len(rows),
            "recordsFiltered": len(rows),  # Adjust if implementing search
            "data": rows,
        }
    )


@api_v1.route("/disable-rules")
@with_db_connection
def disable_rules(conn):
    """Disable rules for a specified number of seconds"""
    seconds = request.args.get("seconds", type=int)
    logging.debug("/disable-rules seconds=%s",seconds)
    if seconds is None:
        return jsonify({"error": "seconds parameter is required"}), 400

    rules_engine.disable_rules(conn, seconds)
    return jsonify({"status": "success", "seconds": seconds})


# Register the blueprint
app.register_blueprint(api_v1, url_prefix="/api/v1")


################################################################
# Serve static files
@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


################################################################
# Top-level routes
@app.route("/")
@with_db_connection
def read_index(conn):
    # Get device data for the template
    device_data = get_last_db_data(conn)

    # Annotate the device_data (same logic as in get_status endpoint)
    for data in device_data:
        if "status" in data:
            data.update(ae200.extract_status(data["status"]))
        if "logtime" in data:
            data["age"] = github_style_duration(
                data["logtime"] + data.get("duration", 1)
            )

    # Add current timestamp for temporal links
    now = int(time.time())

    return render_template("index.html", develop=DEV, devices=device_data, now=now)


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/version")
def get_version():
    return f"version: {__version__}"


@app.route("/rules")
@with_db_connection
def show_rules(conn):
    # Check if we should run the rules or skip them
    run_rules    = request.args.get("run_rules", "1", type=int)  # type: ignore
    rule_results = ""

    # If requests, see how the rules will render for the next seven days
    if run_rules:
        prev_results = ""
        when = datetime.datetime.now().replace(
            minute=0, second=0, microsecond=0
        ) + datetime.timedelta(hours=1)
        for _ in range(24 * 7):
            new_results = rules_engine.rules_results(conn, when.timestamp())
            if new_results and new_results != prev_results:
                rule_results += f"<h3>{str(when)}</h3><pre>{new_results}</pre>\n"
            prev_results = new_results
            when += datetime.timedelta(hours=1)

    rules_disabled_until = rules_engine.rules_disabled_until(conn)
    rules_disabled_until_asc = time.asctime(time.localtime(rules_disabled_until))
    return render_template(
        "rules.html",
        devices=rules_engine.get_devices_dict(conn),
        rules=rules_engine.get_rules(),
        rules_results=rule_results,
        rules_disabled_until=rules_disabled_until,
        rules_disabled_until_asc=rules_disabled_until_asc,
        times=rules_engine.get_time_dict(),
    )


@app.route("/device_log/<device_id>")
@with_db_connection
def device_log(conn, device_id):
    c = conn.cursor()
    c.execute("""SELECT * from devices where device_id=?""", (device_id,))
    device = dict(c.fetchone())

    cmd = """SELECT *,datetime(logtime,'unixepoch','localtime') as start,
                             datetime(logtime+duration,'unixepoch','localtime') as end
                             from devlog where device_id=? """
    args = [device_id]
    (cmd, args) = temporal_quantification(cmd, args)

    cmd += " ORDER BY logtime DESC "

    c.execute(cmd, args)
    devlog = c.fetchall()

    cmd = "SELECT * from changelog where device_id=?"
    args = [device_id]
    (cmd, args) = temporal_quantification(cmd, args)

    cmd += " ORDER BY logtime DESC "

    c.execute(cmd, args)
    changelog = c.fetchall()
    return render_template(
        "device_log.html", device=device, devlog=devlog, changelog=changelog
    )


@app.route("/chart")
def show_chart():
    device_ids_param = request.args.get("device_ids", "")

    # Parse device_ids - can be single value or comma-separated list
    device_ids = None
    if device_ids_param:
        try:
            device_ids = [
                int(did.strip()) for did in device_ids_param.split(",") if did.strip()
            ]
        except ValueError:
            device_ids = None

    return render_template("chart.html", device_ids=device_ids)


# Error handler
@app.errorhandler(HTTPException)
def handle_exception(e):
    return jsonify({"error": e.description}), e.code
