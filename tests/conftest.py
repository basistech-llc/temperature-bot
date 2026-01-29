"""
Pytest configuration and shared fixtures for the temperature-bot test suite.
"""

import os
import tempfile
import sqlite3
import logging
import time
from pathlib import Path

import pytest

from app.main import app as flask_app
from app.paths import SCHEMA_FILE_PATH

DEFAULT_AQI_VALUE = 45
TEST_DEVICE_NAME = "Broadway Test"

# Set environment variables for all tests
os.environ["AE200_SIMULATOR"] = "1"
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(
    Path(__file__).resolve().parents[0].parents[0] / ".playwright"
)

logger = logging.getLogger(__name__)

skip_on_github = pytest.mark.skipif(
    os.getenv("GITHUB_ACTIONS") == "true", reason="Disabled in GitHub Actions"
)


def db_path(conn):
    """Given a database connection, return the filename of the sqlite3 database"""
    # Execute the PRAGMA command
    cursor = conn.cursor()
    cursor.execute("PRAGMA database_list")

    # Fetch the result (it's a list of tuples)
    # Example tuple: (0, 'main', '/full/path/to/my_database.db')
    database_list = cursor.fetchall()

    # Isolate the filename for the 'main' database
    for entry in database_list:
        # entry[1] is the name ('main'), entry[2] is the filename/path
        if entry[1] == "main":
            return entry[2]
    raise FileNotFoundError("Did not find database name")


################################################################
## Reduce logging


@pytest.fixture(scope="session", autouse=True)
def reduce_websockets_logging():
    """Reduce websockets debug logging for tests."""
    logging.getLogger("websockets.client").setLevel(logging.INFO)


################################################################
## Create and access test databsae


@pytest.fixture
def empty_database_conn():
    """Create a temporary test database with schema and return the file path."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        path = tf.name
        # logging.info("Created temporary database file for test: %s", path)

        # Temporarily set an environment variable to tell lifespan we are testing
        os.environ["IS_TESTING"] = "True"
        os.environ["TEST_DB_NAME"] = path

        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        yield conn
        os.environ.pop("TEST_DB_NAME", None)
        os.environ.pop("IS_TESTING", None)
        conn.close()


@pytest.fixture
def test_database_conn(empty_database_conn):
    """
    provides a database populated with schema.sql.
    """
    cursor = empty_database_conn.cursor()
    if not os.path.exists(SCHEMA_FILE_PATH):
        logging.error(
            "Schema file not found at %s. Please ensure it exists.", SCHEMA_FILE_PATH
        )
        raise FileNotFoundError(f"Schema file not found at {SCHEMA_FILE_PATH}")
    with open(SCHEMA_FILE_PATH, "r") as f:
        schema_sql = f.read()
        try:
            cursor.executescript(schema_sql)
            empty_database_conn.commit()
            # logging.info(
            #     "Test database schema set up successfully from %s.", SCHEMA_FILE_PATH
            # )
        except sqlite3.Error as e:
            logging.exception("Test database error during schema setup: %s", e)
            empty_database_conn.rollback()
            raise
    yield empty_database_conn


@pytest.fixture
def test_database_conn_with_test_data(test_database_conn):
    """
    Creates test AQI data and temperature data with records at different time intervals:
    Use this for all tests that require a browser
    """
    # Define time intervals in seconds
    INTERVALS = {
        "1_hour": 1 * 60 * 60,
        "26_hours": 26 * 60 * 60,
        "200_hours": 200 * 60 * 60,
        "2000_hours": 2000 * 60 * 60,
    }
    EXPECTED_COUNTS = {
        "day": 1,  # Only 1 hour ago
        "week": 2,  # 1 hour + 26 hours ago
        "month": 3,  # 1 hour + 26 hours + 200 hours ago
        "all": 4,  # All records
    }

    now = int(time.time())
    cursor = test_database_conn.cursor()
    cursor.execute(
        "INSERT INTO aqi (logtime,aqi) VALUES (?,?)", (now, DEFAULT_AQI_VALUE)
    )
    test_database_conn.commit()

    # Create device
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", (TEST_DEVICE_NAME,))
    device_id = cursor.lastrowid

    # Add records at each interval. Initial speed is always LOW.
    for _, seconds in INTERVALS.items():
        record_time = now - seconds
        cursor.execute(
            """
            INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                device_id,
                record_time,
                60,
                240,
                '{"Drive": "ON", "FanSpeed": "LOW", "InletTemp": "24.0"}',
            ),
        )

    test_database_conn.commit()

    return (test_database_conn, device_id, EXPECTED_COUNTS)


@pytest.fixture
def flask_test_client(test_database_conn_with_test_data):
    """Provides a Flask test client with overridden database connection using a temporary file DB.
    Use this for all tests that do not require a browser
    """
    # Override the database connection function
    logger.debug(
        "flask_test_client; test_database_conn_with_test_data=%s",
        test_database_conn_with_test_data,
    )
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as test_client:
        yield test_client
