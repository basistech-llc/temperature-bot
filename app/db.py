"""
Centralized database operations to sqlite3 database.
Specialized to temperature bot.
Location is specified by environment variable DB_PATH.
Default location is $ROOT_DIR/temperature-bot.db  (largely for development and testing)
"""

import sqlite3
import time  # For logtime timestamps
import logging
import json
import math
import os
import sys

from typing import List, Dict, Any
from pydantic import BaseModel

from flask import request

from .constants import DB_PATH, TEST_DB_NAME
from .paths import SCHEMA_FILE_PATH
from .util import github_style_duration
from . import ae200
from . import airquality
from . import weather

logger = logging.getLogger(__name__)

DEVICE_MAP: dict[str, int] = {}
MAX_DURATION = 3600  # don't extend more than an hour

# Cache the schema file's modification time so we only re-apply the schema
# when the file actually changes on disk. This keeps the convenient
# auto-setup behavior without running the full schema on every request.
# We do this here (rather than at "server startup") because this module
# is also used by CLI tools and schedulers that may not go through a single
# well-defined startup path.
_SCHEMA_MTIME: float | None = None


def reset_schema_mtime_cache() -> None:
    """Reset the schema mtime cache. For use by tests only."""
    global _SCHEMA_MTIME  # pylint: disable=global-statement
    _SCHEMA_MTIME = None


def get_schema_mtime() -> float | None:
    """Return the cached schema mtime. For use by tests only."""
    return _SCHEMA_MTIME


class SpeedControl(BaseModel):
    """Pydantic model for speed control requests."""

    device_id: int
    fan_speed: int


class DriveControl(BaseModel):
    """Pydantic model for speed control requests."""

    device_id: int
    drive: int


class NoteControl(BaseModel):
    """Pydantic model for note update requests."""

    device_id: int
    notes: str | None


class SetTempControl(BaseModel):
    """Pydantic model for set temperature update requests.

    The value is always expressed in Celsius, regardless of UI units.
    """

    device_id: int
    set_temp_c: float


def connect_db(db_path):
    """Establishes a connection to the SQLite database."""
    logger.debug("connect_db(%s)", db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # returns rows as dicts
    conn.execute("PRAGMA foreign_keys=ON;")
    # Use DELETE journal mode for testing to avoid WAL locking issues
    if TEST_DB_NAME in os.environ:
        conn.execute("PRAGMA journal_mode=DELETE;")
    else:
        conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def get_db_connection():
    """
    Returns a new SQLite connection for each request.
    The connection should be closed by the caller when done.
    """
    try:
        # Use test database if in testing environment
        if "TEST_DB_NAME" in os.environ:
            db_path = os.environ[TEST_DB_NAME]
        else:
            db_path = os.environ[DB_PATH]
        conn = connect_db(db_path)

        # Apply schema changes automatically, but only when the schema file
        # has actually changed on disk. This preserves the Poorman migration
        # convenience while avoiding running the full schema on every request.
        # [TODO] This poorman hack should be replaced with real migration management. This lacks
        # rollback and relies on schema.sql not doing anything destructive to an existing DB
        global _SCHEMA_MTIME  # pylint: disable=global-statement
        current_mtime = os.path.getmtime(SCHEMA_FILE_PATH)

        if _SCHEMA_MTIME is None or current_mtime != _SCHEMA_MTIME:
            setup_database(conn, SCHEMA_FILE_PATH)
            _SCHEMA_MTIME = current_mtime

        return conn
    except KeyError as e:
        logger.exception("KeyError: %s", e)
        print("*****************************")
        print("*** Please define DB_PATH *** ", file=sys.stderr)
        print("*****************************")
        raise
    except sqlite3.Error as e:
        logger.exception("Database connection error: %s", e)
        raise


def setup_database(conn, schema_file):
    """
    Creates the necessary tables if they don't exist by reading SQL from a file.
    """
    cursor = conn.cursor()

    try:
        with open(schema_file, "r") as f:
            schema_sql = f.read()
        cursor.executescript(schema_sql)  # Executes all SQL statements in the file
        conn.commit()
        DEVICE_MAP.clear()
        logger.info("Database schema from '%s' set up successfully.", schema_file)
    except sqlite3.Error as e:
        conn.rollback()
        logger.error("Database error during schema setup: %s", e)
        raise  # Re-raise the exception
    except Exception as e:
        conn.rollback()
        logger.exception("An unexpected error occurred during schema setup: %s", e)
        raise


################################################################
## Device management


def get_or_create_device_id(conn, device_name, use_cache=True):
    """
    Retrieves the ID for a given device name. If the device name does not exist
    in the devices table, it inserts it and returns the newly generated ID.
    Don't use the cache when testing
    """
    cursor = conn.cursor()

    if "PYTEST" in os.environ:
        use_cache = False

    if use_cache and (device_name in DEVICE_MAP):
        logger.debug(
            "get_or_create_device_id DEVICE_MAP[%s]=%s",
            device_name,
            DEVICE_MAP[device_name],
        )
        return DEVICE_MAP[device_name]

    try:
        logger.debug("INSERT OR IGNORE device_name=%s", device_name)
        cursor.execute(
            "INSERT OR IGNORE INTO devices (device_name) VALUES (?);", (device_name,)
        )
        conn.commit()

        cursor.execute("SELECT * FROM devices WHERE device_name = ?;", (device_name,))
        result = cursor.fetchone()

        if result:
            logger.debug(
                "get_or_create_device_id(%s) result=%s", device_name, dict(result)
            )
            DEVICE_MAP[device_name] = result["device_id"]
            return DEVICE_MAP[device_name]
        else:
            logger.error("Could not retrieve ID for device name: %s", device_name)
            raise ValueError("Could not retrieve ID for device name: %s" % device_name)  # pylint: disable=consider-using-f-string

    except sqlite3.Error as e:
        logger.error("Database error in get_or_create_device_id: %s", e)
        conn.rollback()  # Rollback any partial transaction
        raise  # Re-raise the exception


def fetch_all_devices(conn):
    """Fetches all device names and their IDs."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM devices;")
    return cursor.fetchall()


def fetch_all_device_dicts(conn):
    """Fetches all device names and their IDs."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM devices;")
    return cursor.fetchall()


def devices_to_device_id(conn):
    """Return a dictionary of device_name:device_id"""
    c = conn.cursor()
    c.execute("SELECT * from devices order by device_name")
    ret = {
        dev["device_name"].replace(" ", "_").upper(): dev["device_id"]
        for dev in c.fetchall()
    }
    logging.debug("ret=%s", ret)
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


################################################################
## devlog - log of what happened


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
        cursor.execute(
            """
            SELECT d.*, dn.device_name
            FROM devlog d
            JOIN devices dn ON d.device_id = dn.device_id
            WHERE d.device_id = ? AND (d.logtime + d.duration) > ?
            ORDER BY d.logtime DESC
        """,
            (device_id, cutoff_time),
        )

        return cursor.fetchall()

    except sqlite3.Error as e:
        logger.error("Database error in get_recent_devlogs: %s", e)
        raise
    except ValueError as e:
        logger.error("Error: %s", e)
        raise


# Insertion
# pylint: disable=too-many-arguments, disable=too-many-positional-arguments
def insert_devlog_entry(
    conn,
    *,
    device_id=None,
    device_name: str | None = None,
    temp=None,
    statusdict=None,
    logtime=None,
    force=False,
    commit=True,
):
    """
    :param conn: database connection
    :param device_id: the device_id
    :param device_name: the device (if device_id is not provided)
    :param temp: Temperature in C
    :param statusdict: If provided, a dictionary that will be written to the database as status_json (but not if extending)
    :param logtime: The time_t of the log. If not provided, it's now!
    :param force: If True, forces a new entry.
                  If False, then only create a new entry if the temp or statusdict have changed.
    Inserts an entry into the devlog table, handling the device_id lookup/creation and automatic extension.
    """
    logger.debug(
        "device_id=%s device_name=%s temp=%s logtime=%s force=%s commit=%s",
        device_id,
        device_name,
        temp,
        logtime,
        force,
        commit,
    )
    temp10x = int(math.floor(float(temp) * 10 + 0.5)) if temp else None
    status_json = (
        json.dumps(statusdict, default=str, sort_keys=True) if statusdict else None
    )
    c = conn.cursor()
    if logtime is None:
        logtime = int(time.time())  # Use current Unix timestamp if not provided
    try:
        # Get or create the device_id
        if device_id is None:
            assert device_name is not None
            device_id = get_or_create_device_id(conn, device_name)

        # Get the most recent temperature entry. If temperature matches and we are not forcing, extend it.
        c.execute(
            "SELECT * from devlog where device_id=? and logtime<=? order by logtime DESC limit 1",
            (device_id, logtime),
        )
        r = c.fetchone()
        if r and r["logtime"] == logtime:
            # duplicate entry. Replace if duration is 1
            if r["duration"] == 1:
                logger.debug("replace with temp10x=%s status=%s", temp10x, status_json)
                c.execute(
                    "UPDATE devlog set temp10x=?,status_json=? where log_id=?",
                    (temp10x, status_json, r["log_id"]),
                )
            else:
                logger.debug(
                    "ignore temp10x=%s status=%s because row=%s",
                    temp10x,
                    status_json,
                    dict(r),
                )
            return

        if (
            r
            and r["temp10x"] == temp10x
            and r["status_json"] == status_json
            and not force
        ):
            duration = logtime - r["logtime"] + 1
            if duration < MAX_DURATION:
                logger.info(
                    "Updated devlog entry: device_id=%s temp10x=%s logtime=%s duration=%s",
                    device_id,
                    temp10x,
                    time.asctime(time.localtime(r["logtime"])),
                    duration,
                )
                c.execute(
                    "UPDATE devlog set duration=? where log_id=?",
                    (duration, r["log_id"]),
                )
                if commit:
                    conn.commit()
                return

        # Insert into devlog using the obtained device_id
        logger.debug("insert logtime=%s device_id=%s", logtime, device_id)
        c.execute(
            "INSERT INTO devlog (logtime, device_id, temp10x, status_json) VALUES (?, ?, ?, ?);",
            (logtime, device_id, temp10x, status_json),
        )
        if commit:
            conn.commit()
        logger.info(
            "Inserted devlog entry: device_id=%s, temp10x=%s", device_id, temp10x
        )
    except sqlite3.Error as e:
        logger.error("Database error in insert_devlog_entry: %s", e)
        conn.rollback()  # Rollback any partial transaction
        raise
    except ValueError as e:
        logger.error("Error: %s", e)
        conn.rollback()
        raise


def insert_changelog(
    conn,
    *,
    ipaddr: str,
    device_id: int,
    ae200_device_id: int,
    current_values: str = "",
    new_value: str,
    agent: str = "",
    comment: str = "",
):
    assert ae200_device_id is not None, "ae200_device_id must be provided"
    logtime = int(time.time())
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO changelog (logtime, ipaddr, device_id, unit, current_values, new_value, agent, comment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            logtime,
            ipaddr,
            device_id,
            ae200_device_id,
            current_values,
            new_value,
            agent,
            comment,
        ),
    )
    conn.commit()


def update_devlog_map(conn, device_name: str, ae200_device_id: int):
    logger.debug("device_name=%s ae200_device_id=%s", device_name, ae200_device_id)
    c = conn.cursor()
    device_id = get_or_create_device_id(conn, device_name)
    c.execute(
        "UPDATE devices set ae200_device_id = ? where device_id=?",
        (ae200_device_id, device_id),
    )
    conn.commit()
    return device_id


################################################################
## Rules
def device_rules_disabled_until(conn, device_id: int) -> int | None:
    """
    :param conn: - database connection
    :param device_id: - device_id
    :return: time_t that rules are disabled until, or None if they are no longer disabled
    """
    c = conn.cursor()
    c.execute("SELECT disabled_until from devices where device_id=?", (device_id,))
    row = c.fetchone()
    return row[0] if row is not None else None


def disable_rules_for_device(
    conn, device_id: int, seconds: int, ipaddr=None, agent=None, comment=None
):
    """Disable the rules for this device for a given number of seconds."""
    now = int(time.time())
    if seconds == 0:
        until = 0
    else:
        until = now + seconds
    c = conn.cursor()

    # Get the old value
    c.execute("SELECT disabled_until from devices where device_id=?", (device_id,))
    was = c.fetchone()
    current_value = was[0] if was else None

    # Update the disabled until and then the changelog
    c.execute(
        "UPDATE devices set disabled_until=? where device_id=?", (until, device_id)
    )

    # Write the log entry
    c.execute(
        """
        INSERT INTO changelog (logtime, ipaddr, device_id, current_values, new_value, agent, comment)
        VALUES (?,?,?,?,?,?,?)
        """,
        (now, ipaddr, device_id, current_value, until, agent, comment),
    )
    conn.commit()


def update_device_notes(conn, device_id: int, notes: str | None):
    """Update the notes field for a device."""
    logger.debug("update_device_notes: device_id=%s, notes=%s", device_id, notes)
    c = conn.cursor()
    c.execute("UPDATE devices SET notes=? WHERE device_id=?", (notes, device_id))
    conn.commit()
    return device_id


################################################################
## AE200
def get_ae200_unit(conn, device_id: int):
    c = conn.cursor()
    c.execute("select ae200_device_id from devices where device_id=?", (device_id,))
    ret = c.fetchone()["ae200_device_id"]
    logger.debug("device_id=%s ae200_unit=%d", device_id, ret)
    return ret


################################################################
## AQI and Temperature


def temporal_quantification(cmd, args):
    """Annotate cmd and args with start, end, limit"""
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
## AQI
def get_last_aqi(conn):
    c = conn.cursor()
    c.execute("select aqi from aqi order by logtime DESC limit 1")
    aqi = c.fetchone()[0]
    logger.debug("last_aqi=%s", aqi)
    return aqi


def get_aqi_series(conn):
    c = conn.cursor()
    cmd = """ SELECT * from aqi where 1 """
    (cmd, args) = temporal_quantification(cmd, [])
    cmd += " ORDER BY logtime "
    c.execute(cmd, args)
    rows = c.fetchall()
    if not rows:
        return []
    keys = [k for k in rows[0].keys() if k != "logtime"]
    return {key: [[row["logtime"], row[key]] for row in rows] for key in keys}


def get_temperature_series(
    conn, device_ids: List[int] | None = None
) -> List[Dict[str, Any]]:
    """Get temperature series data for devices.
    :param device_ids: a list of integer device IDs or None. An empty list or None gets all devices
    :return: a list of dicts each in the form {name:"name", data:[[time1,val1], [time2,val2], ...]}
    """
    c = conn.cursor()
    # Get all devices
    c.execute("SELECT * from devices")
    devices = c.fetchall()
    if not device_ids:
        device_ids = [dev["device_id"] for dev in devices]

    series = []
    for dev in devices:
        if dev["device_id"] in device_ids:
            cmd = """
            SELECT logtime,temp10x from devlog
            WHERE device_id=? AND logtime IS NOT NULL AND temp10x IS NOT NULL
            """
            args = [dev["device_id"]]
            (cmd, args) = temporal_quantification(cmd, args)
            cmd += " ORDER BY logtime "
            c.execute(cmd, args)
            rows = c.fetchall()
            data = [[row["logtime"], row["temp10x"] / 10] for row in rows]
            if data:
                series.append({"name": dev["device_name"], "data": data})
    return series


def get_device_status(conn) -> List[Dict[str, Any]]:
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


def get_changelog(
    conn, draw: int = 1, start_row: int = 0, length: int = 100
) -> Dict[str, Any]:
    """Get changelog data with pagination"""
    cmd = """SELECT c.logtime, c.ipaddr, d.device_name as unit, c.new_value, c.agent, c.comment FROM changelog c
               LEFT JOIN devices d ON c.device_id = d.device_id WHERE 1=1"""
    args: List[Any] = []

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

    return {
        "draw": draw,
        "recordsTotal": len(rows),
        "recordsFiltered": len(rows),  # Adjust if implementing search
        "data": rows,
    }


def get_device_log(conn, device_id: int) -> Dict[str, Any]:
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

    return {"device": device, "devlog": devlog, "changelog": changelog}


def insert_into_aqi(conn, values):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO aqi (logtime,aqi,co,h,no2,o3,p,pm10,pm25,so2,t,w) values (:logtime,:aqi,:co,:h,:no2,:o3,:p,:pm10,:pm25,:so2,:t,:w)",
        values,
    )
    conn.commit()


def get_db_aqi(conn) -> dict:
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


def get_aqi_and_weather_data(conn) -> dict:
    """Get combined weather and AQI data"""
    aqi_data = get_db_aqi(conn)
    weather_data = weather.get_weather_data()
    return {"aqi": aqi_data, "weather": weather_data}
