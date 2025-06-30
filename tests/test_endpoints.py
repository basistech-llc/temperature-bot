#import asyncio
import logging
from unittest.mock import AsyncMock, patch
import sqlite3
import os
#import time
import pytest_asyncio
import pytest
import tempfile # Import tempfile
#import shutil   # Import shutil for directory cleanup

from fastapi.testclient import TestClient
# from contextlib import asynccontextmanager # Not directly used on override_get_db_connection

from myapp.main import app as fastapi_app
import myapp.ae200 as ae200
import myapp.aqi as aqi
import myapp.db as db
#from myapp.main import status, set_speed, SpeedControl

logger = logging.getLogger(__name__)

# Optional: enable pytest-asyncio
pytest_plugins = ("pytest_asyncio",)

# Path to the schema file in the parent directory
SCHEMA_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'etc', 'schema.sql')

# Override the setup_database function for testing
def setup_test_database(conn):
    """
    Sets up the database schema on a given connection by reading from schema.sql.
    """
    cursor = conn.cursor()
    try:
        if not os.path.exists(SCHEMA_FILE_PATH):
            logging.error("Schema file not found at %s. Please ensure it exists.", SCHEMA_FILE_PATH)
            raise FileNotFoundError("Schema file not found at %s" % SCHEMA_FILE_PATH)

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

# Dependency override for testing with a real temporary file database
# CHANGED: Removed db_path argument; it will now read from os.environ['TEST_DB_NAME']
async def get_test_db_connection_provider():
    """
    Provides a temporary, file-based SQLite connection for tests.
    This is an async generator compatible with FastAPI's Depends().
    """
    conn = None
    try:
        # Connect to the temporary file database using the environment variable
        temp_db_path = os.environ['TEST_DB_NAME'] # Get the path from the environment
        conn = sqlite3.connect(temp_db_path)
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
            logging.debug("Test database connection closed for %s.", os.environ.get('TEST_DB_NAME', 'unknown'))

# Set up the TestClient and apply the dependency override
@pytest_asyncio.fixture(scope="function")
async def client():
    """Provides a TestClient with overridden database dependency using a temporary file DB."""
    # Create a temporary directory for the database file
    with tempfile.TemporaryDirectory() as tmpdir:
        # Generate a unique path for the database file within the temporary directory
        temp_db_path = os.path.join(tmpdir, "test_db.sqlite")
        logging.info("Created temporary database file for test: %s", temp_db_path)

        # Temporarily set an environment variable to tell lifespan we are testing
        os.environ['IS_TESTING'] = 'True'
        # IMPORTANT: Also set TEST_DB_NAME environment variable for db.py's get_db_connection
        # to ensure it connects to this temporary file.
        os.environ['TEST_DB_NAME'] = temp_db_path

        # Override the dependency provider.
        # CHANGED: Assign the async generator function directly, as its signature now matches.
        fastapi_app.dependency_overrides[db.get_db_connection] = get_test_db_connection_provider

        with TestClient(fastapi_app) as test_client:
            yield test_client

        # Clean up the override and environment variables after the test
        fastapi_app.dependency_overrides.clear()
        os.environ.pop("IS_TESTING", None)
        os.environ.pop("TEST_DB_NAME", None) # Clean up the TEST_DB_NAME env var
        # The TemporaryDirectory context manager will automatically delete tmpdir and its contents.
        logging.info("Cleaned up temporary database directory: %s", tmpdir)


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
@patch("myapp.ae200.get_all_status", new_callable=AsyncMock)
async def test_status_endpoint(mock_get_all_status,client): # Needs client to ensure DB setup
    mock_get_all_status.return_value = [{'name':'test-device','drive':'ON','speed':'HIGH','val':4}]

    # If this status endpoint also uses db.get_db_connection,
    # it will now correctly use the overridden test DB.
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    response_json = response.json()
    assert "ALL" in response_json
    assert "AQI" in response_json
    logging.info(" /status: %s", response_json)


@pytest.mark.asyncio
@pytest.mark.parametrize("unit,speed", [
    (12, 0),
    (12, 1),
    (13, 2),
])
@patch("myapp.ae200.set_fan_speed", new_callable=AsyncMock)
async def test_set_speed_endpoint(mock_set_fan_speed, client, unit, speed):
    response = client.post(
        "/api/v1/set_speed", # Adjust this path to your actual endpoint URL
        json={"unit": unit, "speed": speed} # Send data as JSON body
    )
    assert response.status_code == 200 # Check for successful HTTP status
    response_json = response.json()
    assert response_json["status"] == "ok"
    assert response_json["unit"] == unit
    assert response_json["speed"] == speed

    # This verifies that myapp.ae200.set_fan_speed is called once with (unit,speed) as arguments
    mock_set_fan_speed.assert_awaited_once_with(unit, speed)

    # Now, you can actually query the test database to verify the changelog entry
    # Get a new connection to the test DB to verify the data
    # IMPORTANT: Connect to the same temporary file database
    with sqlite3.connect(os.environ['TEST_DB_NAME']) as test_conn_verify:
        test_conn_verify.row_factory = sqlite3.Row
        cursor = test_conn_verify.cursor()
        # Note: Assumes 'changelog' table is part of your etc/schema.sql
        cursor.execute("SELECT ipaddr, unit, new_value, agent FROM changelog WHERE unit = ? AND new_value = ?;", (unit, str(speed)))
        changelog_entry = cursor.fetchone()

        assert changelog_entry is not None
        # In test, client.ipaddr is 'testclient' by default for TestClient
        assert changelog_entry['ipaddr'] == 'testclient'
        assert changelog_entry['unit'] == unit
        assert changelog_entry['new_value'] == str(speed)
        assert changelog_entry['agent'] == 'web'

    logging.info("/set_speed (unit=%s, speed=%s):", unit, speed)
