import sqlite3
import time # For logtime timestamps
import logging
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
logger.error("DATABASE_NAME=%s",DATABASE_NAME)

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
        logging.info("Database schema from '%s' set up successfully.", schema_file)
    except sqlite3.Error as e:
        conn.rollback()
        logging.error("Database error during schema setup: %s", e)
        raise # Re-raise the exception
    except Exception as e:
        conn.rollback()
        logging.exception("An unexpected error occurred during schema setup: %s", e)
        raise


def get_or_create_sensor_id(conn, sensor_name):
    """
    Retrieves the ID for a given sensor name. If the sensor name does not exist
    in the sensor_names table, it inserts it and returns the newly generated ID.
    """
    cursor = conn.cursor()

    try:
        # Attempt to insert the sensor name.
        # IGNORE ensures that if it already exists (due to UNIQUE constraint),
        # no error is raised and nothing new is inserted.
        cursor.execute("INSERT OR IGNORE INTO sensor_names (name) VALUES (?);", (sensor_name,))
        conn.commit() # Commit the insert operation

        # Now, retrieve the ID of the sensor name, whether it was just inserted
        # or already existed.
        cursor.execute("SELECT id FROM sensor_names WHERE name = ?;", (sensor_name,))
        result = cursor.fetchone()

        if result:
            return result['id']
        else:
            # This case should ideally not happen if INSERT OR IGNORE works as expected
            # and SELECT follows immediately, but it's good for robustness.
            logging.error("Could not retrieve ID for sensor name: %s", sensor_name)
            raise ValueError("Could not retrieve ID for sensor name: %s" % sensor_name) # Using %s for consistency

    except sqlite3.Error as e:
        logging.error("Database error in get_or_create_sensor_id: %s", e)
        conn.rollback() # Rollback any partial transaction
        raise # Re-raise the exception


def insert_templog_entry(conn, sensor_name, temp10x, logtime=None):
    """
    Inserts an entry into the templog table, handling the sensor_id lookup/creation.
    """
    if logtime is None:
        logtime = int(time.time()) # Use current Unix timestamp if not provided

    try:
        # Get or create the sensor_id
        sensor_id = get_or_create_sensor_id(conn, sensor_name)

        # Insert into templog using the obtained sensor_id
        cursor = conn.cursor()
        cursor.execute("INSERT INTO templog (logtime, sensor_id, temp10x) VALUES (?, ?, ?);",
                       (logtime, sensor_id, temp10x) )
        conn.commit()
        # Changed to logging.info
        logging.info("Inserted templog entry: sensor='%s' (ID: %s), temp10x=%s", sensor_name, sensor_id, temp10x)
    except sqlite3.Error as e:
        logging.error("Database error in insert_templog_entry: %s", e)
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

def fetch_all_templog_with_sensor_names(conn):
    """
    Fetches all templog entries, joining with sensor_names to display the sensor string.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            t.id,
            t.logtime,
            s.name AS sensor_name,
            t.temp10x
        FROM
            templog t
        JOIN
            sensor_names s ON t.sensor_id = s.id
        ORDER BY
            t.logtime DESC;
    """)
    return cursor.fetchall()

def fetch_all_sensor_names(conn):
    """Fetches all sensor names and their IDs."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM sensor_names;")
    return cursor.fetchall()
