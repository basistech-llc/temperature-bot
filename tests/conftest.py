"""
Pytest configuration and shared fixtures for the temperature-bot test suite.
"""
import os
import tempfile
import sqlite3
import logging
import time
import pytest

from app import db
from app.paths import SCHEMA_FILE_PATH
from app.main import app as flask_app

from tests.helpers.test_utils import create_test_database_with_schema

# Set AE200_SIMULATOR environment variable for all tests
os.environ['AE200_SIMULATOR'] = '1'

logger = logging.getLogger(__name__)

skip_on_github = pytest.mark.skipif( os.getenv("GITHUB_ACTIONS") == "true",
                                     reason="Disabled in GitHub Actions" )

def insert_temporal_test_data(conn: sqlite3.Connection, device_name: str = "Test Device"):
    """
    Creates test data with records at different time intervals:
    - 1 hour ago
    - 26 hours ago
    - 200 hours ago
    - 2000 hours ago

    Returns the device_id and a dict with the expected record counts for different time ranges.
    """
    logger.info("insert_temporal_test_data")
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
    for _, seconds in intervals.items():
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
def test_db_connection():
    """Provides a test database connection."""
    with tempfile.NamedTemporaryFile(suffix='.db') as tf:
        os.environ['TEST_DB_PATH'] = tf.name
        os.environ['IS_TESTING'] = 'TRUE'
        yield db.get_db_connection(SCHEMA_FILE_PATH, testing=True)
        os.environ.pop("TEST_DB_PATH")
        os.environ.pop("IS_TESTING", None)

@pytest.fixture
def test_db_name():
    """Provides a test database file name."""
    tf_name = create_test_database_with_schema()

    # Set environment variable for the test
    os.environ['TEST_DB_PATH'] = tf_name
    yield tf_name

    # Clean up
    os.environ.pop("TEST_DB_PATH", None)
    os.unlink(tf_name)


@pytest.fixture
def client_with_db(test_db_connection):
    """Provides a Flask test client with overridden database connection using a temporary file DB."""
    # Override the database connection function
    _ = test_db_connection      # make sure it is created, but ignore it here
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reduce_websockets_logging():
    """Reduce websockets debug logging for tests."""
    logging.getLogger("websockets.client").setLevel(logging.INFO)
