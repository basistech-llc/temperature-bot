import sqlite3
import time # For logtime timestamps
import logging
import json
import math
from pathlib import Path
import os   # For checking file existence
# Removed HTTPException and status import as they are not used directly here
# from fastapi import HTTPException, status # Removed, these belong in main.py if used

logger = logging.getLogger(__name__) # Use __name__ for module-specific logging

DB_PATH = '/var/db/temperature-bot.db'
LOCAL_DB_PATH = Path(__file__).parent.parent / "storage.db"
DB_PATH = Path(DB_PATH) if os.path.exists(DB_PATH) else LOCAL_DB_PATH

# Dummy DATABASE_NAME for development if not set via environment (should be configured in main.py or env)
# In a real app, DATABASE_NAME should come from an environment variable or app config.
# For testing, it's overridden.
DATABASE_NAME = os.getenv("DATABASE_NAME", str(DB_PATH))
logger.debug("DATABASE_NAME=%s",DATABASE_NAME)

DEVICE_MAP = {}

def connect_db(db_name):
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row      # returns rows as dicts
    conn.execute("PRAGMA foreign_keys = ON;") # Ensure foreign keys are enabled
    return conn

async def get_db_connection():
    """
    Dependency that opens a new SQLite connection for each request
    and ensures it's closed after the request is processed.
    """
    conn = None
    try:
        conn = connect_db(DATABASE_NAME) # This connect_db function is your synchronous one
        yield conn # Provide the connection to the route function
    except sqlite3.Error as e:
        # Re-raising HTTPException here is generally done in the FastAPI route
        # or a custom exception handler, not directly in a db utility.
        # But for now, keeping it consistent with previous logic while fixing f-string
        logging.exception("Database connection error in dependency: %s", e)
        # Assuming HTTPException is imported in main.py for actual app use.
        # If this is strictly a DB utility, you might raise a custom DB exception instead.
        raise # Re-raise the exception after logging
    finally:
        if conn:
            conn.close()
            logging.debug("Database connection closed for request.")

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
        DEVICE_MAP = {}
        logging.info("Database schema from '%s' set up successfully.", schema_file)
    except sqlite3.Error as e:
        conn.rollback()
        logging.error("Database error during schema setup: %s", e)
        raise # Re-raise the exception
    except Exception as e:
        conn.rollback()
        logging.exception("An unexpected error occurred during schema setup: %s", e)
        raise

def get_or_create_device_id(conn, device_name):
    """
    Retrieves the ID for a given device name. If the device name does not exist
    in the devices table, it inserts it and returns the newly generated ID.
    """
    cursor = conn.cursor()

    if device_name in DEVICE_MAP:
        return DEVICE_MAP[device_name]

    try:
        cursor.execute("INSERT OR IGNORE INTO devices (device_name) VALUES (?);", (device_name,))
        conn.commit()

        cursor.execute("SELECT device_id FROM devices WHERE device_name = ?;", (device_name,))
        result = cursor.fetchone()

        if result:
            DEVICE_MAP[device_name] = result['device_id']
            return DEVICE_MAP[device_name]
        else:
            logging.error("Could not retrieve ID for device name: %s", device_name)
            raise ValueError("Could not retrieve ID for device name: %s" % device_name) # Using %s for consistency

    except sqlite3.Error as e:
        logging.error("Database error in get_or_create_device_id: %s", e)
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

# Insertion

def insert_devlog_entry(conn, device_name: str, temp=None, statusdict=None, logtime=None, force=False, commit=True):
    """
    :param conn: database connection
    :param device_name: the device
    :param temp10x: (Temperature in C) * 10
    :param statusdict: If provided, a dictionary that will be written to the database as status_json (but not if extending)
    :param logtime: The time_t of the log. If not provided, it's now!
    :param force: If True, forces a new entry.
                  If False, then only create a new entry if the temp or statusdict have changed.
    Inserts an entry into the devlog table, handling the device_id lookup/creation and automatic extension.
    """
    temp10x     = int(math.floor(float(temp)*10+0.5)) if temp else None
    status_json = json.dumps(statusdict, default=str, sort_keys=True) if statusdict else None
    c = conn.cursor()
    if logtime is None:
        logtime = int(time.time()) # Use current Unix timestamp if not provided
    try:
        # Get or create the device_id
        device_id = get_or_create_device_id(conn, device_name)

        # Get the most recent temperature entry. If temperature matches and we are not forcing, extend it.
        c.execute("SELECT * from devlog where device_id=? order by logtime DESC limit 1",(device_id,))
        r = c.fetchone()
        if r and r['temp10x']==temp10x and r['status_json']==status_json and not force:
            duration = logtime-r['logtime']+1
            logging.debug("update log_id=%s duration=%s",device_id,duration)
            c.execute("UPDATE devlog set duration=? where log_id=?",(duration, r['log_id']))
            if commit:
                conn.commit()
            return

        # Insert into devlog using the obtained device_id
        logging.debug("insert logtime=%s device_id=%s",logtime, device_id)
        c.execute("INSERT INTO devlog (logtime, device_id, temp10x, status_json) VALUES (?, ?, ?, ?);",
                       (logtime, device_id, temp10x, status_json))
        if commit:
            conn.commit()
        # Changed to logging.info
        logging.info("Inserted devlog entry: device='%s' (ID: %s), temp10x=%s", device_name, device_id, temp10x)
    except sqlite3.Error as e:
        logging.error("Database error in insert_devlog_entry: %s", e)
        conn.rollback() # Rollback any partial transaction
    except ValueError as e:
        logging.error("Error: %s", e)
        conn.rollback()

def insert_changelog( conn, ipaddr:str, unit: int, new_value: str, agent: str = "", comment: str = ""):
    logtime = int(time.time())
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO changelog (logtime, ipaddr, unit, new_value, agent, comment)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (logtime, ipaddr, unit, new_value, agent, comment))
    conn.commit()
