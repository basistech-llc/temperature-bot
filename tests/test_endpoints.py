import asyncio
import logging
from unittest.mock import AsyncMock, patch
import sqlite3
import os
import time
import pytest_asyncio
import pytest

from fastapi.testclient import TestClient
from contextlib import asynccontextmanager

from myapp.main import app as fastapi_app
import myapp.ae200 as ae200
import myapp.aqi as aqi
import myapp.db as db
from myapp.main import status, set_speed, SpeedControl

logger = logging.getLogger(__name__)

# Optional: enable pytest-asyncio
pytest_plugins = ("pytest_asyncio",)

# Define a temporary in-memory database name for tests
TEST_DB_NAME = ":memory:" # Use in-memory database for speed and isolation
SCHEMA_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'etc', 'schema.sql')

# Override the setup_database function for testing
# This setup_database will now take a connection and set up schema on it
def setup_test_database(conn):
    """
    Sets up the database schema on a given connection by reading from schema.sql.
    """
    cursor = conn.cursor()
    try:
        if not os.path.exists(SCHEMA_FILE_PATH):
            logging.error("Schema file not found at %s. Please ensure it exists.", SCHEMA_FILE_PATH)
            raise FileNotFoundError(f"Schema file not found at {SCHEMA_FILE_PATH}")

        with open(SCHEMA_FILE_PATH, 'r') as f:
            schema_sql = f.read()

        cursor.executescript(schema_sql)
        conn.commit()
        logging.info("Test database schema set up successfully from %s.", SCHEMA_FILE_PATH)
    except sqlite3.Error as e:
        logging.exception("Test database error during schema setup: %s", e)
        conn.rollback()
    except Exception as e:
        logging.exception("An unexpected error occurred during test schema setup: %s", e)
        conn.rollback()

# Dependency override for testing with a real in-memory database
async def override_get_db_connection():
    """
    Provides a temporary, in-memory SQLite connection for tests.
    """
    conn = None
    try:
        # Connect to an in-memory database
        conn = sqlite3.connect(TEST_DB_NAME)
        print(f"**** conn(id)={conn(id)}  db={TEST_DB_NAME}")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;") # Ensure foreign keys are enabled

        # Set up schema on this temporary connection
        setup_test_database(conn)

        yield conn # Yield the connection to the test
    except Exception as e:
        logging.exception("Error setting up test database connection: %s", e)
        raise
    finally:
        if conn:
            conn.close()
            logging.debug("Test database connection closed.")

# Set up the TestClient and apply the dependency override
# This part is crucial for making the TestClient use our test DB
@pytest_asyncio.fixture(scope="function")
async def client():
    """Provides a TestClient with overridden database dependency."""
    # Temporarily override the dependency for this test scope
    os.environ['IS_TESTING'] = 'True'
    fastapi_app.dependency_overrides[db.get_db_connection] = override_get_db_connection

    # The TestClient will now use the overridden dependency
    with TestClient(fastapi_app) as test_client:
        yield test_client

    # Clean up the override after the test
    fastapi_app.dependency_overrides.clear()

# Use pytest-asyncio to allow async test functions
@pytest.mark.asyncio
async def test_get_aqi_sync():
    result = aqi.get_aqi_sync()
    assert isinstance(result, dict)
    assert "value" in result
    logging.info("get_aqi_sync: %s", result)

@pytest.mark.asyncio
async def test_get_erv_status():
    result = await ae200.get_erv_status()
    assert isinstance(result, dict)
    logging.info(" get_erv_status: %s", result)

@pytest.mark.asyncio
async def test_status_endpoint():
    response = await status()
    assert "AQI" in response and "ERV" in response
    logging.info(" /status: %s", response)

@pytest.mark.asyncio
@pytest.mark.parametrize("unit,speed", [
    (12, 0),
    (12, 1),
    (13, 2),
])
@patch("myapp.ae200.set_erv_speed", new_callable=AsyncMock)
async def test_set_speed_endpoint(mock_set_speed, client, unit, speed):
    response = client.post(
        "/api/v1/set_speed", # Adjust this path to your actual endpoint URL
        json={"unit": unit, "speed": speed} # Send data as JSON body
    )
    assert response.status_code == 200 # Check for successful HTTP status
    response_json = response.json()
    assert response_json["status"] == "ok"
    assert response_json["unit"] == unit
    assert response_json["speed"] == speed

    # This verifies that myapp.ae200.set_erv_speed is called once with (unit,speed) as arguments
    mock_set_speed.assert_awaited_once_with(unit, speed)

    # Now, you can actually query the test database to verify the changelog entry
    # Get a new connection to the test DB to verify the data
    with sqlite3.connect(TEST_DB_NAME) as test_conn_verify:
        test_conn_verify.row_factory = sqlite3.Row
        cursor = test_conn_verify.cursor()
        # Note: Assumes 'changelog' table is part of your etc/schema.sql
        cursor.execute("SELECT host, unit, speed, source FROM changelog WHERE unit = ? AND speed = ?;", (unit, str(speed)))
        changelog_entry = cursor.fetchone()

        assert changelog_entry is not None
        # In test, client.host is 'testclient' by default for TestClient
        assert changelog_entry['host'] == 'testclient'
        assert changelog_entry['unit'] == unit
        assert changelog_entry['speed'] == str(speed)
        assert changelog_entry['source'] == 'web'

    logging.info("/set_speed (unit=%s, speed=%s):", unit, speed)
