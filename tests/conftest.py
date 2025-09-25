"""
Pytest configuration and shared fixtures for the temperature-bot test suite.
"""
import os
import tempfile
import sqlite3
import logging
import time
import pytest
from app.main import app as flask_app
from app.paths import SCHEMA_FILE_PATH

# Set AE200_SIMULATOR environment variable for all tests
os.environ['AE200_SIMULATOR'] = '1'

logger = logging.getLogger(__name__)

skip_on_github = pytest.mark.skipif(
    os.getenv("GITHUB_ACTIONS") == "true",
    reason="Disabled in GitHub Actions"
)


def setup_test_database(conn):
    """
    Sets up the database schema on a given connection by reading from schema.sql.
    """
    logging.debug("*** setup_test_database")
    cursor = conn.cursor()
    try:
        if not os.path.exists(SCHEMA_FILE_PATH):
            logging.error("Schema file not found at %s. Please ensure it exists.", SCHEMA_FILE_PATH)
            raise FileNotFoundError(f"Schema file not found at {SCHEMA_FILE_PATH}")

        with open(SCHEMA_FILE_PATH, 'r') as f:
            schema_sql = f.read()

        cursor.executescript(schema_sql)
        conn.commit()
        cursor.execute("INSERT INTO aqi VALUES (?,?)", (int(time.time()), 45))  # insert AQI of 45
        logging.debug("*** sending schema")
        logging.info("Test database schema set up successfully from %s.", SCHEMA_FILE_PATH)
    except sqlite3.Error as e:
        logging.exception("Test database error during schema setup: %s", e)
        conn.rollback()


def insert_temporal_test_data(conn: sqlite3.Connection, device_name: str = "Test Device"):
    """
    Creates test data with records at different time intervals:
    - 1 hour ago
    - 26 hours ago
    - 200 hours ago
    - 2000 hours ago

    Returns the device_id and a dict with the expected record counts for different time ranges.
    """
    current_time = int(time.time())

    # Create device
    cursor = conn.cursor()
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", (device_name,))
    device_id = cursor.lastrowid

    # Define time intervals in seconds
    intervals = {
        "1_hour": 1 * 60 * 60,
        "26_hours": 26 * 60 * 60,
        "200_hours": 200 * 60 * 60,
        "2000_hours": 2000 * 60 * 60
    }

    # Add records at each interval. Initial speed is always LOW.
    for interval_name, seconds in intervals.items():  # pylint: disable=unused-variable
        record_time = current_time - seconds
        cursor.execute("""
            INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
            VALUES (?, ?, ?, ?, ?)
        """, (device_id, record_time, 60, 240, '{"Drive": "ON", "FanSpeed": "LOW", "InletTemp": "24.0"}'))

    conn.commit()

    # Calculate expected record counts for different time ranges
    expected_counts = {
        "day": 1,    # Only 1 hour ago
        "week": 2,   # 1 hour + 26 hours ago
        "month": 3,  # 1 hour + 26 hours + 200 hours ago
        "all": 4     # All records
    }

    return device_id, expected_counts


@pytest.fixture
def client():
    """Provides a Flask test client with overridden database connection using a temporary file DB."""
    from tests.helpers.test_utils import create_test_database_with_schema  # pylint: disable=import-outside-toplevel
    # Create a temporary directory for the database file
    create_test_database_with_schema()

    # Override the database connection function
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        yield test_client

    # Clean up the environment variables after the test
    os.environ.pop("IS_TESTING", None)
    os.environ.pop("TEST_DB_NAME", None)


@pytest.fixture
def test_db_connection():
    """Provides a test database connection."""
    with tempfile.NamedTemporaryFile(suffix='.db') as tf:
        conn = sqlite3.connect(tf.name)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        setup_test_database(conn)
        yield conn
        conn.close()


@pytest.fixture
def test_db_name():
    """Provides a test database file name."""
    from tests.helpers.test_utils import create_test_database_with_schema  # pylint: disable=import-outside-toplevel
    tf_name = create_test_database_with_schema()

    # Set environment variable for the test
    os.environ['TEST_DB_NAME'] = tf_name
    yield tf_name

    # Clean up
    os.environ.pop("TEST_DB_NAME", None)
    os.unlink(tf_name)


@pytest.fixture(autouse=True)
def reduce_websockets_logging():
    """Reduce websockets debug logging for tests."""
    logging.getLogger("websockets.client").setLevel(logging.INFO)
