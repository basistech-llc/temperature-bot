"""
app.py - Flask version
"""

from os.path import abspath
import os
import logging
import json
import datetime
from functools import wraps

from flask import Flask, request, jsonify, render_template, send_from_directory, Blueprint
from werkzeug.exceptions import HTTPException

from flask_pydantic import validate

from . import ae200
from . import weather
from . import db
from . import airnow
from . import rules_engine
from .db import SpeedControl

__version__ = '0.0.1'

DEV = "/home/simsong" in abspath(__file__)
API_V1_PREFIX = "/api/v1"
DEFAULT_LOG_LEVEL = 'DEBUG'
LOGGING_CONFIG='%(asctime)s  %(filename)s:%(lineno)d %(levelname)s: %(message)s'
LOG_LEVEL = os.getenv("LOG_LEVEL",DEFAULT_LOG_LEVEL).upper()

ENABLE_AIRNOW = False

logging.basicConfig(format=LOGGING_CONFIG, level=LOG_LEVEL, force=True)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def fix_boto_log_level():
    """Do not run boto loggers at debug level"""
    for name in logging.root.manager.loggerDict: # pylint: disable=no-member
        if name.startswith('boto'):
            logging.getLogger(name).setLevel(logging.INFO)

# https://flask.palletsprojects.com/en/stable/config/
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.logger.setLevel(logging.DEBUG)


# Initialize logging and boto settings
fix_boto_log_level()

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

def get_cached_aqi(conn, cache_hours=1):
    """
    Get AQI data from cache if available and recent, otherwise fetch from API.

    :param conn: database connection
    :param cache_hours: number of hours to cache AQI data
    :return: AQI data dict with value, color, name
    """
    cache_seconds = cache_hours * 3600

    # Check for recent AQI data in database
    if recent_logs:= db.get_recent_devlogs(conn, 'aqi', cache_seconds):
        latest_log = recent_logs[0]
        logger.debug("latest_log=%s",latest_log)
        if latest_log['temp10x']:
            return json.loads(latest_log['temp10x'])

    try:
        if not ENABLE_AIRNOW:
            return {'error':f'ENABLE_AIRNOW={ENABLE_AIRNOW}'}
        aqi_data = airnow.get_aqi_sync()
        if 'error' in aqi_data:
            logger.error("aqi_data=%s", aqi_data)
        else:
            logger.debug("aqi_data=%s",aqi_data)
            db.insert_devlog_entry(conn, device_name='aqi', temp=aqi_data['value'])
        return aqi_data

    except airnow.AirnowError as api_error:
        logger.error("api_error=%s",api_error)
        return {"value": "N/A", "color": "#cccccc", "name": "Unavailable"}

def get_last_db_data(conn):
    def fix_status_json(devdict):
        devdict = dict(devdict)
        try:
            devdict['status'] = json.loads(devdict['status_json'])
        except (TypeError,json.JSONDecodeError):
            pass
        del devdict['status_json']
        return devdict
    return [fix_status_json(dd) for dd in db.fetch_last_status(conn)]

################################################################
# Versioned API routes

api_v1 = Blueprint('api_v1', __name__)

@api_v1.route('/version')
def get_version_json():
    return jsonify({"version": __version__})

@api_v1.route('/set_speed', methods=['POST'])
@validate()
@with_db_connection
def set_speed(conn, body: SpeedControl):
    """Sets the speed, records the speed in the changelog, and then updates the database, so status is always up-to-date"""
    logger.info("set speed: body=%s",body)
    ret = rules_engine.set_body_speed(conn, body, request.remote_addr, 'web')
    logging.debug("ret=%s",ret)
    return jsonify({ "status": "ok", **ret })

@api_v1.route('/status')
@with_db_connection
def get_status(conn):
    device_data = get_last_db_data(conn)

    # Annotate the device_data
    for data in device_data:
        if data.get('status', []):
            data.update(ae200.extract_status(data['status']))

    return jsonify({"devices": device_data})

@api_v1.route('/weather')
@with_db_connection
def get_weather(conn):
    aqi_data = get_cached_aqi(conn, cache_hours=1)
    weather_data = weather.get_weather_data()

    return jsonify({"aqi": aqi_data, "weather": weather_data})

@api_v1.route('/logs')
@with_db_connection
def get_logs(conn):
    start = request.args.get('start', type=int)
    end = request.args.get('end', type=int)
    draw = request.args.get('draw', 1, type=int)
    start_row = request.args.get('start_row', 0, type=int)
    length = request.args.get('length', 100, type=int)

    query = "SELECT c.logtime, c.ipaddr, d.device_name as unit, c.new_value, c.agent, c.comment FROM changelog c LEFT JOIN devices d ON c.device_id = d.device_id WHERE 1=1"
    params = []

    if start is not None:
        query += " AND logtime >= ?"
        params.append(start)
    if end is not None:
        query += " AND logtime <= ?"
        params.append(end)

    query += " ORDER BY logtime DESC LIMIT ? OFFSET ?"
    params.extend([length, start_row])
    logger.info("query=%s params=%s", query, params)

    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM changelog")
    total_records = c.fetchone()[0]
    c.execute(query, params)
    data = [dict(row) for row in c.fetchall()]  # Convert Row objects to dicts for JSON serialization

    return jsonify({
        "draw": draw,
        "recordsTotal": total_records,
        "recordsFiltered": total_records,  # Adjust if implementing search
        "data": data
    })

# Register the blueprint
app.register_blueprint(api_v1, url_prefix='/api/v1')

################################################################
# Serve static files
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

################################################################
# Top-level routes
@app.route("/")
def read_index():
    return render_template("index.html", develop=DEV)

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/version")
def get_version():
    return f"version: {__version__}"


@app.route("/rules")
@with_db_connection
def show_rules(conn):
    # Let's see how the rules will render for the next seven days
    rule_results = ""
    prev_results = ""
    when = datetime.datetime.now().replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
    for _ in range(24*7):
        new_results = rules_engine.rules_results(conn, when.timestamp())
        if new_results and new_results != prev_results:
            rule_results += f"<h3>{str(when)}</h3><pre>{new_results}</pre>\n"
        prev_results = new_results
        when += datetime.timedelta(hours=1)

    print('rule_results=',rule_results)

    return render_template("rules.html",
                           devices=rules_engine.get_devices_dict(conn),
                           rules=rules_engine.get_rules(),
                           rules_results=rule_results,
                           times=rules_engine.get_time_dict())

@app.route("/device_log/<device_id>")
@with_db_connection
def device_log(conn, device_id):
    c = conn.cursor()
    c.execute("""SELECT *,datetime(logtime,'unixepoch','localtime') as start,
                             datetime(logtime+duration,'unixepoch','localtime') as end
                             from devlog where device_id=? order by logtime desc""",(device_id,))
    rows = c.fetchall()
    logger.debug("rows=%s",[dict(row) for row in rows])
    return render_template("device_log.html",rows=rows)

# Error handler
@app.errorhandler(HTTPException)
def handle_exception(e):
    return jsonify({"error": e.description}), e.code

print(f"main.py: app id={id(app)}")
