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

from pydantic import BaseModel, conint

from app.paths import DB_PATH

logger = logging.getLogger(__name__)
logger.debug("DB_PATH=%s",DB_PATH)

DEVICE_MAP = {}

class SpeedControl(BaseModel):
    """Pydantic model for speed control requests."""
    device_id: conint(ge=0, le=20)
    speed: conint(ge=0, le=4)

def connect_db(db_name):
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row      # returns rows as dicts
    conn.execute("PRAGMA foreign_keys=ON;")
    # Use DELETE journal mode for testing to avoid WAL locking issues
    if 'TEST_DB_NAME' in os.environ:
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
        if 'TEST_DB_NAME' in os.environ:
            db_path = os.environ['TEST_DB_NAME']
        else:
            db_path = DB_PATH
        logger.debug("db_path=%s",db_path)
        conn = connect_db(db_path)
        return conn
    except sqlite3.Error as e:
        logger.exception("Database connection error: %s", e)
        raise

def setup_database(conn, schema_file):
    """
    Creates the necessary tables if they don't exist by reading SQL from a file.
    """
    cursor = conn.cursor()

    try:
        with open(schema_file, 'r') as f:
            schema_sql = f.read()
        cursor.executescript(schema_sql) # Executes all SQL statements in the file
        conn.commit()
        DEVICE_MAP.clear()
        logger.info("Database schema from '%s' set up successfully.", schema_file)
    except sqlite3.Error as e:
        conn.rollback()
        logger.error("Database error during schema setup: %s", e)
        raise # Re-raise the exception
    except Exception as e:
        conn.rollback()
        logger.exception("An unexpected error occurred during schema setup: %s", e)
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
            logger.debug("get_or_create_device_id(%s) result=%s",device_name,result)
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
            t.id, t.logtime, s.name AS device_name, t.temp10x
        FROM
            devlog t
        JOIN
            devices s ON t.device_id = s.device_id
        ORDER BY
            t.logtime DESC;
    """)
    return cursor.fetchall()

def fetch_all_devices(conn):
    """Fetches all device names and their IDs."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM devices;")
    return cursor.fetchall()

def fetch_last_status(conn):
    """Fetches the last status for each device"""
    cursor = conn.cursor()
    cursor.execute("""SELECT a.*,b.device_name
                      FROM (SELECT * FROM devlog GROUP BY device_id HAVING logtime=max(logtime)) AS a
                      LEFT JOIN devices b where a.device_id = b.device_id
                      ORDER by b.device_name""")
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
                        device_id=None, device_name: str=None, temp=None, statusdict=None,
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
            # duplicate entry. Replace if duration is
            if r['duration']==1:
                logger.debug("replace %s with temp10x=%s status=%s",dict(r),temp10x,status_json)
                c.execute("UPDATE devlog set temp10x=?,status_json=? where log_id=?",(temp10x, status_json,r['log_id']))
            else:
                logger.debug("ignore temp10x=%s status=%s because row=%s",temp10x,status_json,dict(r))
            return

        if r and r['temp10x']==temp10x and r['status_json']==status_json and not force:
            duration = logtime-r['logtime']+1
            logger.debug("update log_id=%s temp10x=%s duration=%s",device_id,temp10x,duration)
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
        logger.info("Inserted devlog entry: device_name='%s' device_id=%s, temp10x=%s", device_name, device_id, temp10x)
    except sqlite3.Error as e:
        logger.error("Database error in insert_devlog_entry: %s", e)
        conn.rollback() # Rollback any partial transaction
        raise
    except ValueError as e:
        logger.error("Error: %s", e)
        conn.rollback()
        raise

def insert_changelog( conn, ipaddr:str, device_id: int, new_value: str, agent: str = "", comment: str = ""):
    logtime = int(time.time())
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO changelog (logtime, ipaddr, device_id, new_value, agent, comment)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (logtime, ipaddr, device_id, new_value, agent, comment))
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
    return c.fetchone()['ae200_device_id']
