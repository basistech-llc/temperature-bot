"""
Centralized database operations to sqlite3 database.
Specialized to temperature bot.
Location is specified by environment variable DB_PATH.
Default location is $ROOT_DIR/temperature-bot.db  (largely for development and testing)
"""

import sqlite3
import time # For logtime timestamps
import logging
import json
import math
import os
from functools import wraps
from pathlib import Path

from typing import Optional,Dict,List,Any

from flask import request
from pydantic import BaseModel

from . import ae200
from . import airquality
from . import weather_getter
from .paths import db_path
from .utils.time_utils import github_style_duration
from .utils.query_utils import temporal_quantification

logger = logging.getLogger(__name__)


DEVICE_MAP: dict[str, int] = {}
MAX_DURATION=3600                 # don't extend more than an hour

class SpeedControl(BaseModel):
    """Pydantic model for speed control requests."""
    device_id: int
    fan_speed: int

class DriveControl(BaseModel):
    """Pydantic model for speed control requests."""
    device_id: int
    drive: int

def _connect_db(db_name,testing=False):
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row      # returns rows as dicts
    conn.execute("PRAGMA foreign_keys=ON;")
    # Use DELETE journal mode for testing to avoid WAL locking issues
    if testing:
        conn.execute("PRAGMA journal_mode=DELETE;")
    else:
        conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def get_db_connection(*,db_path_name=None,schema_file=None, testing=False):
    """
    Returns a new SQLite connection for each request.
    The connection should be closed by the caller when done.
    """
    try:
        # Use test database if in testing environment

        if db_path_name is not None:
            pth = Path(db_path_name)
        else:
            pth = db_path()
        if (schema_file is None) and (not pth.exists()):
            raise FileNotFoundError(pth)
        conn = _connect_db(str(pth),testing=testing)
        if schema_file is not None:
            try:
                cursor = conn.cursor()
                with open(schema_file, 'r') as f:
                    schema_sql = f.read()
                cursor.executescript(schema_sql) # Executes all SQL statements in the file
                conn.commit()
                logger.info("Created %s with schema %s", pth, schema_file)
                return conn
            except sqlite3.Error as e:
                conn.rollback()
                logger.error("Database error during schema setup: %s", e)
                raise # Re-raise the exception
        logger.info("Opened %s",pth)
        return conn
    except sqlite3.Error as e:
        logger.exception("Database connection error: %s", e)
        raise

def get_or_create_device_id(conn, device_name, use_cache=True):
    """
    Retrieves the ID for a given device name. If the device name does not exist
    in the devices table, it inserts it and returns the newly generated ID.
    Don't use the cache when testing
    """
    cursor = conn.cursor()

    if 'PYTEST' in os.environ:
        use_cache = False

    if use_cache and (device_name in DEVICE_MAP):
        logger.debug("get_or_create_device_id DEVICE_MAP[%s]=%s",device_name,DEVICE_MAP[device_name])
        return DEVICE_MAP[device_name]

    try:
        logger.debug("INSERT OR IGNORE device_name=%s",device_name)
        cursor.execute("INSERT OR IGNORE INTO devices (device_name) VALUES (?);", (device_name,))
        conn.commit()

        cursor.execute("SELECT * FROM devices WHERE device_name = ?;", (device_name,))
        result = cursor.fetchone()

        if result:
            logger.debug("get_or_create_device_id(%s) result=%s",device_name,dict(result))
            DEVICE_MAP[device_name] = result['device_id']
            return DEVICE_MAP[device_name]
        else:
            logger.error("Could not retrieve ID for device name: %s", device_name)
            raise ValueError("Could not retrieve ID for device name: %s" % device_name) # pylint: disable=consider-using-f-string

    except sqlite3.Error as e:
        logger.error("Database error in get_or_create_device_id: %s", e)
        conn.rollback() # Rollback any partial transaction
        raise # Re-raise the exception

def fetch_all_devlog_with_devices(conn):
    """
    Fetches all devlog entries, joining with devices to display the device string.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            t.id, t.logtime, s.name AS device_name, t.temp10x, s.notes
        FROM
            devlog t
        JOIN
            devices s ON t.device_id = s.device_id
        ORDER BY
            t.logtime DESC;
    """)
    return cursor.fetchall()

#def fetch_all_devices(conn):
#    """Fetches all device names and their IDs."""
#    cursor = conn.cursor()
#    cursor.execute("SELECT id, device_name FROM devices;")
#    return cursor.fetchall()

def get_devices_dict(conn):
    """Add all of the devices in the devices table to the global environment"""
    c = conn.cursor()
    c.execute("SELECT * from devices order by device_name")
    ret = {dev['device_name'].replace(' ','_').upper() : dev['device_id'] for dev in c.fetchall()}
    logging.debug("ret=%s",ret)
    return ret

def fetch_last_status(conn):
    """Fetches the last status for each device"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.*,b.device_name,b.notes,b.disabled_until
        FROM (SELECT * FROM devlog GROUP BY device_id HAVING logtime=max(logtime)) AS a
        LEFT JOIN devices b where a.device_id = b.device_id
        ORDER by b.device_name""")
    return cursor.fetchall()

def fetch_last_status_fixed(conn):
    """Runs db.fetch_last_status(conn) and then converts `status_json` into the actual dictionary for each status_json object"""
    def fix_status_json(devdict):
        devdict = dict(devdict)
        try:
            devdict["status"] = json.loads(devdict["status_json"])
        except (TypeError, json.JSONDecodeError):
            pass
        del devdict["status_json"]
        return devdict

    return [fix_status_json(dd) for dd in fetch_last_status(conn)]


def get_recent_devlogs(conn, device_name: str, seconds: int):
    """
    Get recent devlog entries for a device within the specified time window.

    :param conn: database connection
    :param device_name: the device name to query
    :param seconds: number of seconds to look back from now
    :return: list of devlog entries where logtime+duration > now()-seconds
    """
    cursor = conn.cursor()
    current_time = int(time.time())
    cutoff_time = current_time - seconds

    try:
        # Get the device_id
        device_id = get_or_create_device_id(conn, device_name)

        # Query for entries where logtime+duration > cutoff_time
        # This ensures we get the most recent entry AND any other entry that overlaps with our time window
        cursor.execute("""
            SELECT d.*, dn.device_name
            FROM devlog d
            JOIN devices dn ON d.device_id = dn.device_id
            WHERE d.device_id = ? AND (d.logtime + d.duration) > ?
            ORDER BY d.logtime DESC
        """, (device_id, cutoff_time))

        return cursor.fetchall()

    except sqlite3.Error as e:
        logger.error("Database error in get_recent_devlogs: %s", e)
        raise
    except ValueError as e:
        logger.error("Error: %s", e)
        raise

# Insertion
# pylint: disable=too-many-arguments, disable=too-many-positional-arguments
def insert_devlog_entry(conn, *,
                        device_id=None, device_name: str | None = None, temp=None, statusdict=None,
                        logtime=None, force=False, commit=True):
    """
    :param conn: database connection
    :param device_id: the device_id
    :param device_name: the device (if device_id is not provided)
    :param temp10x: (Temperature in C) * 10
    :param statusdict: If provided, a dictionary that will be written to the database as status_json (but not if extending)
    :param logtime: The time_t of the log. If not provided, it's now!
    :param force: If True, forces a new entry.
                  If False, then only create a new entry if the temp or statusdict have changed.
    Inserts an entry into the devlog table, handling the device_id lookup/creation and automatic extension.
    """
    logger.debug("conn=%s device_id=%s device_name=%s temp=%s statusdict=%s logtime=%s force=%s commit=%s",
                  conn,device_id, device_name,temp,statusdict,logtime,force,commit)
    temp10x     = int(math.floor(float(temp)*10+0.5)) if temp else None
    status_json = json.dumps(statusdict, default=str, sort_keys=True) if statusdict else None
    c = conn.cursor()
    if logtime is None:
        logtime = int(time.time()) # Use current Unix timestamp if not provided
    try:
        # Get or create the device_id
        if device_id is None:
            assert device_name is not None
            device_id = get_or_create_device_id(conn, device_name)

        # Get the most recent temperature entry. If temperature matches and we are not forcing, extend it.
        c.execute("SELECT * from devlog where device_id=? and logtime<=? order by logtime DESC limit 1",(device_id,logtime))
        r = c.fetchone()
        if r and r['logtime']==logtime:
            # duplicate entry. Replace if duration is 1
            if r['duration']==1:
                logger.debug("replace %s with temp10x=%s status=%s",dict(r),temp10x,status_json)
                c.execute("UPDATE devlog set temp10x=?,status_json=? where log_id=?",(temp10x, status_json,r['log_id']))
            else:
                logger.debug("ignore temp10x=%s status=%s because row=%s",temp10x,status_json,dict(r))
            return

        if r and r['temp10x']==temp10x and r['status_json']==status_json and not force:
            duration = logtime-r['logtime']+1
            if duration < MAX_DURATION:
                logger.info("Updated devlog entry: device_id=%s temp10x=%s logtime=%s duration=%s",device_id,temp10x,time.asctime(time.localtime(r['logtime'])),duration)
                c.execute("UPDATE devlog set duration=? where log_id=?",(duration, r['log_id']))
                if commit:
                    conn.commit()
                return

        # Insert into devlog using the obtained device_id
        logger.debug("insert logtime=%s device_id=%s",logtime, device_id)
        c.execute("INSERT INTO devlog (logtime, device_id, temp10x, status_json) VALUES (?, ?, ?, ?);",
                       (logtime, device_id, temp10x, status_json))
        if commit:
            conn.commit()
        logger.info("Inserted devlog entry: device_id=%s, temp10x=%s", device_id, temp10x)
    except sqlite3.Error as e:
        logger.error("Database error in insert_devlog_entry: %s", e)
        conn.rollback() # Rollback any partial transaction
        raise
    except ValueError as e:
        logger.error("Error: %s", e)
        conn.rollback()
        raise

def insert_changelog(conn, *, ipaddr: str, device_id: int, ae200_device_id: int, current_values: str="", new_value: str, agent: str = "", comment: str = ""):
    assert ae200_device_id is not None, "ae200_device_id must be provided"
    logtime = int(time.time())
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO changelog (logtime, ipaddr, device_id, unit, current_values, new_value, agent, comment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (logtime, ipaddr, device_id, ae200_device_id, current_values, new_value, agent, comment))
    conn.commit()

def update_devlog_map(conn, device_name:str, ae200_device_id:int):
    logger.debug("device_name=%s ae200_device_id=%s",device_name,ae200_device_id)
    c = conn.cursor()
    device_id = get_or_create_device_id(conn, device_name)
    c.execute("UPDATE devices set ae200_device_id = ? where device_id=?",(ae200_device_id, device_id))
    conn.commit()
    return device_id

def get_ae200_unit(conn, device_id:int):
    c = conn.cursor()
    c.execute("select ae200_device_id from devices where device_id=?",(device_id,))
    ret = c.fetchone()['ae200_device_id']
    logger.debug("device_id=%s ae200_unit=%d",device_id,ret)
    return ret

def get_last_aqi(conn):
    c = conn.cursor()
    c.execute("select aqi from aqi order by logtime DESC limit 1")
    aqi = c.fetchone()[0]
    logger.debug("last_aqi=%s",aqi)
    return aqi


################################################################
## Rules Disabling.
## Rules can be disabled per-device until a particular time
################################################################

def disable_rules_report(conn, device_id:Optional[int]=None):
    """Rules are enabled by default. This returns a dictionary of all devices and when the rules are disabled until.
    :param device_id: just for this device
    :return: a dictionary where key=device_id and value={:device_id, :device_name, :disabled_until}
    """
    c = conn.cursor()
    if device_id is not None:
        c.execute("SELECT device_id,device_name,disabled_until from devices where device_id=?",(device_id,))
    else:
        c.execute("SELECT device_id,device_name,disabled_until from devices")
    return {dev['device_id']:dev for dev in c.fetchall()}

def disable_rules(conn, device_id:int, seconds:int):
    """Enter a database engtry to disable the rules until a specific time.
    device_id=0 means all devices.
    """
    now=int(time.time())
    logging.debug("disable_rules device_id=%s seconds=%s",device_id, seconds)
    if seconds==0:
        msg = json.dumps({'comment':'enable rules', 'seconds':seconds, 'device_id':device_id})
        disabled_until = 0
    else:
        disabled_until = now+seconds
        asc_when = time.asctime(time.localtime(disabled_until))
        msg = json.dumps({'comment':f'disable rules until {asc_when}',
                          'device_id':device_id,
                          'seconds':seconds})
    logging.debug("disable_rules(seconds=%s,msg=%s,device_id=%s) now=%s disabled_until=%s",
                  seconds,msg,device_id,now,disabled_until)
    c = conn.cursor()
    c.execute("INSERT INTO changelog (logtime, ipaddr, device_id, new_value) VALUES (?,?,?,?)",
              (time.time(), request.remote_addr, device_id, msg))
    if device_id==0:
        logging.debug("setting disabled_until to %s for all devices",disabled_until)
        c.execute("UPDATE devices set disabled_until=?",(disabled_until,))
    else:
        c.execute("UPDATE devices set disabled_until=? WHERE device_id=?",(disabled_until, device_id))
    conn.commit()


class DB:
    """Simple cover to provide a contexst manager"""
    def __init__(self,db_path_name=None):
        self.conn = get_db_connection(db_path_name=db_path_name)

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()


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


class LogService:
    """Service for log-related operations"""

    def __init__(self):
        self.logger = logger

    def get_changelog(self, conn, draw: int = 1, start_row: int = 0, length: int = 100) -> Dict[str, Any]:
        """Get changelog data with pagination"""
        cmd = """SELECT c.logtime, c.ipaddr, d.device_name as unit, c.new_value, c.agent, c.comment FROM changelog c
                   LEFT JOIN devices d ON c.device_id = d.device_id WHERE 1=1"""
        args: List[Any] = []

        (cmd, args) = temporal_quantification(cmd, args)

        cmd += " ORDER BY logtime DESC LIMIT ? OFFSET ?"
        args.extend([length, start_row])
        self.logger.debug("cmd=%s args=%s", cmd, args)

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

        return {
            "draw": draw,
            "recordsTotal": len(rows),
            "recordsFiltered": len(rows),  # Adjust if implementing search
            "data": rows,
        }

    def get_device_log(self, conn, device_id: int) -> Dict[str, Any]:
        """Get device log data"""

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

        return {
            "device": device,
            "devlog": devlog,
            "changelog": changelog
        }

class DeviceService:
    """Service for device-related operations"""

    def __init__(self):
        self.logger = logger

    def get_device_status(self, conn) -> List[Dict[str, Any]]:
        """Get device status with annotations"""
        device_data = fetch_last_status_fixed(conn)

        # Extract and convert the top-level drive, speed, and other items
        for data in device_data:
            if "status" in data:
                data.update(ae200.extract_drive_and_fan_speed(data["status"]))
            if "logtime" in data:
                data["age"] = github_style_duration(
                    data["logtime"] + data.get("duration", 1)
                )

        return device_data

    def get_temperature_series(self, conn, device_ids: List[int] = None) -> List[Dict[str, Any]]:
        """Get temperature series data for devices"""

        c = conn.cursor()
        series = []

        if device_ids:
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

        return series

class WeatherService:
    """Service for weather and AQI operations"""

    def __init__(self):
        self.logger = logger

    def get_db_aqi(self, conn) -> dict:
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

    def get_weather_data(self, conn) -> dict:
        """Get combined weather and AQI data"""
        aqi_data = self.get_db_aqi(conn)
        weather_data = weather_getter.get_weather_data()
        return {"aqi": aqi_data, "weather": weather_data}
