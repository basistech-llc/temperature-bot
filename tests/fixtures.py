#!/usr/bin/env python3
"""
Simple test to check if Flask routes are working
"""
import os
import tempfile
import sqlite3
import logging
import time
import pytest
from app.main import app as flask_app
from app.paths import SCHEMA_FILE_PATH

skip_on_github = pytest.mark.skipif(os.getenv("GITHUB_ACTIONS") == "true", reason="Disabled in GitHub Actions")

# Override the setup_database function for testing
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
        logging.debug("*** sending schema")
        logging.info("Test database schema set up successfully from %s.", SCHEMA_FILE_PATH)
    except sqlite3.Error as e:
        logging.exception("Test database error during schema setup: %s", e)
        conn.rollback()

def create_temporal_test_data(conn, device_name="Test Device"):
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

    # Add records at each interval
    for interval_name, seconds in intervals.items():
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
    # Create a temporary directory for the database file
    with tempfile.NamedTemporaryFile(suffix='.db') as tf:
        logging.info("Created temporary database file for test: %s", tf.name)

        # Temporarily set an environment variable to tell lifespan we are testing
        os.environ['IS_TESTING'] = 'True'
        # IMPORTANT: Also set TEST_DB_NAME environment variable for db.py's get_db_connection
        # to ensure it connects to this temporary file.
        os.environ['TEST_DB_NAME'] = tf.name

        # Set up the database schema in the temporary file
        conn = sqlite3.connect(tf.name)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        setup_test_database(conn)
        conn.close()

        # Override the database connection function
        flask_app.config['TESTING'] = True
        with flask_app.test_client() as test_client:
            yield test_client

        # Clean up the environment variables after the test
        os.environ.pop("IS_TESTING", None)
        os.environ.pop("TEST_DB_NAME", None)
