"""
test async endpoints
"""
#import asyncio
from os.path import join
import logging
from unittest.mock import AsyncMock, patch
import sqlite3
import os
import tempfile # Import tempfile
import json
#import time
import pytest_asyncio
import pytest
#import shutil   # Import shutil for directory cleanup

from fastapi.testclient import TestClient
# from contextlib import asynccontextmanager # Not directly used on override_get_db_connection

from app.main import app as fastapi_app
from app import main
from app import ae200
from app import airnow
from app import db
from app.paths import SCHEMA_FILE_PATH,TEST_DATA_DIR
#from app.main import status, set_speed, SpeedControl

logger = logging.getLogger(__name__)

# Optional: enable pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


# Disable websockets debug
@pytest.fixture(autouse=True)
def reduce_websockets_logging():
    logging.getLogger("websockets.client").setLevel(logging.INFO)

skip_on_github = pytest.mark.skipif( os.getenv("GITHUB_ACTIONS") == "true", reason="Disabled in GitHub Actions")

# Override the setup_database function for testing
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
        logging.exception("wild")
        c = conn.cursor()
        c.execute("select * from devices")
        for row in c.fetchall():
            logging.exception("ROW=%s",dict(row))
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
    with tempfile.NamedTemporaryFile(suffix='.db') as tf:
        logging.info("Created temporary database file for test: %s", tf.name)

        # Temporarily set an environment variable to tell lifespan we are testing
        os.environ['IS_TESTING'] = 'True'
        # IMPORTANT: Also set TEST_DB_NAME environment variable for db.py's get_db_connection
        # to ensure it connects to this temporary file.
        os.environ['TEST_DB_NAME'] = tf.name

        # Override the dependency provider.
        # CHANGED: Assign the async generator function directly, as its signature now matches.
        fastapi_app.dependency_overrides[db.get_db_connection] = get_test_db_connection_provider

        with TestClient(fastapi_app) as test_client:
            yield test_client

        # Clean up the override and environment variables after the test
        fastapi_app.dependency_overrides.clear()
        os.environ.pop("IS_TESTING", None)
        os.environ.pop("TEST_DB_NAME", None)


@pytest.mark.asyncio
async def test_get_version(client):
    response = client.get("/version")
    assert response.status_code == 200
    assert response.text == f'version: {main.__version__}'

    response = client.get("/api/v1/version")
    assert response.status_code == 200
    assert response.json() == {'version':main.__version__}


# Use pytest-asyncio to allow async test functions
@skip_on_github
@pytest.mark.asyncio
@patch("app.airnow.get_aqi_sync")
async def test_get_aqi_sync(mock_get_aqi_sync):
    # Mock the return value
    mock_get_aqi_sync.return_value = {"value": 45, "color": "#00e400", "name": "Good"}

    result = airnow.get_aqi_sync()
    assert isinstance(result, dict)
    assert "value" in result
    assert result["value"] == 45
    assert result["name"] == "Good"
    logging.info("get_aqi_sync: %s", result)

@skip_on_github
async def test_status_endpoint(client): # Needs client to ensure DB setup
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    response_json = response.json()
    logging.info(" /status: %s", response_json)
    assert "devices" in response_json

@skip_on_github
@pytest.mark.asyncio
@patch("app.weather.get_weather_data_async", new_callable=AsyncMock)
@patch("app.airnow.get_aqi_async", new_callable=AsyncMock)
async def test_weather_endpoint(mock_get_weather_data, mock_get_aqi, client): # Needs client to ensure DB setup
    mock_get_aqi.return_value = {"value": 45, "color": "#00e400", "name": "Good"}
    mock_get_weather_data.return_value = {"current": {"temperature": 72, "conditions": "Sunny"}, "forecast": []}

    # If this status endpoint also uses db.get_db_connection,
    # it will now correctly use the overridden test DB.
    response = client.get("/api/v1/weather")
    assert response.status_code == 200
    response_json = response.json()
    logging.info(" /weather: %s", response_json)
    assert "aqi" in response_json
    assert "weather" in response_json


# pylint: disable=too-many-arguments, disable=too-many-positional-arguments
@pytest.mark.asyncio
@pytest.mark.parametrize("unit,speed,name", [
    (10, 0, "OFF"),             # Run for unit 10 (Broadway South)
#    (10, 1, "LOW"),
#    (10, 4, "HIGH"),
])
@patch("app.ae200.get_device_info_async", new_callable=AsyncMock)
@patch("app.ae200.set_fan_speed_async", new_callable=AsyncMock)
@patch("app.ae200.get_devices_async", new_callable=AsyncMock) # note patche args are in reverse order
async def test_set_speed_endpoint(mock_get_devices_async,mock_set_fan_speed_async, mock_get_device_info_async, client, unit, speed, name):
    # Get the mocked return value
    with open(join(TEST_DATA_DIR,'get_devices.json')) as f:
        mock_get_devices_async.return_value = json.load(f)
    with open(join(TEST_DATA_DIR,'get_device_10.json')) as f:
        dev10 = json.load(f)
        dev10['FanSpeed'] = name        # it should be set to this name
        mock_get_device_info_async.return_value = dev10


    # Send the /set_speed
    response = client.post(
        "/api/v1/set_speed",
        json={"unit": unit, "speed": speed}
    )
    assert response.status_code == 200 # Check for successful HTTP status
    response_json = response.json()
    assert response_json["status"] == "ok"
    assert response_json["unit"] == unit
    assert response_json["speed"] == speed
    assert 'device_name' in response_json
    device_name = response_json['device_name']

    # Verify that these were both called with the arguments

    mock_get_devices_async.assert_awaited_once_with()
    mock_get_device_info_async.assert_awaited_once_with(unit)
    mock_set_fan_speed_async.assert_awaited_once_with(unit, speed)

    # Verify that the database got updated
    # Note that we are using the TEST_DB_NAME put in the environment.
    with sqlite3.connect(os.environ['TEST_DB_NAME']) as test_conn_verify:
        test_conn_verify.row_factory = sqlite3.Row
        cursor = test_conn_verify.cursor()
        cursor.execute("SELECT ipaddr, unit, new_value, agent FROM changelog WHERE unit = ? AND new_value = ?;",
                       (unit, str(speed)))
        changelog_entry = cursor.fetchone()

        assert changelog_entry is not None
        assert changelog_entry['ipaddr'] == 'testclient'
        assert changelog_entry['unit'] == unit
        assert changelog_entry['new_value'] == str(speed)
        assert changelog_entry['agent'] == 'web'

        cursor.execute("SELECT * from devices where device_name=?",(device_name,))
        row = cursor.fetchone()
        logging.debug("row=%s",dict(row))
        device_id = row['device_id']
        cursor.execute("SELECT * from devlog where device_id=? order by logtime desc",(device_id,))
        row = cursor.fetchone()
        extracted_status = ae200.extract_status(json.loads(row['status_json']))
        assert extracted_status['drive_speed_val'] == speed

    logging.info("/set_speed (unit=%s, speed=%s):", unit, speed)
