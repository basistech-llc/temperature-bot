"""
test Flask endpoints
"""
from os.path import join
import logging
from unittest.mock import patch
import sqlite3
import os
import json
import pytest

from app import main
from app import ae200
from app.paths import TEST_DATA_DIR

from .fixtures import client, skip_on_github  # noqa: F401  # pylint: disable=unused-import

logger = logging.getLogger(__name__)


# Disable websockets debug
@pytest.fixture(autouse=True)
def reduce_websockets_logging():
    logging.getLogger("websockets.client").setLevel(logging.INFO)


def test_get_version(client):   # noqa: F811
    response = client.get("/version")
    assert response.status_code == 200
    assert response.data.decode('utf-8') == f'version: {main.__version__}'

    response = client.get("/api/v1/version")
    assert response.status_code == 200
    assert response.json == {'version': main.__version__}


def test_status_endpoint(client):  # noqa: F811
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    response_json = response.json
    logging.info(" /status: %s", response_json)
    assert "devices" in response_json

@skip_on_github
@patch("app.weather.get_weather_data")
@patch("app.airnow.get_aqi_sync")
def test_weather_endpoint(mock_get_aqi, mock_get_weather_data, client):  # noqa: F811
    mock_get_aqi.return_value = {"value": 45, "color": "#00e400", "name": "Good"}
    mock_get_weather_data.return_value = {"current": {"temperature": 72, "conditions": "Sunny"}, "forecast": []}

    # If this status endpoint also uses db.get_db_connection,
    # it will now correctly use the overridden test DB.
    response = client.get("/api/v1/weather")
    assert response.status_code == 200
    response_json = response.json
    logging.info(" /weather: %s", response_json)
    assert "aqi" in response_json
    assert "weather" in response_json


# pylint: disable=too-many-arguments, disable=too-many-positional-arguments
@pytest.mark.parametrize("unit,speed,name", [
    (10, 0, "OFF"),             # Run for unit 10 (Broadway South)
#    (10, 1, "LOW"),
#    (10, 4, "HIGH"),
])
@patch("app.ae200.get_device_info")
@patch("app.ae200.set_fan_speed")
@patch("app.ae200.get_devices")  # note patch args are in reverse order
def test_set_speed_endpoint(mock_get_devices, mock_set_fan_speed, mock_get_device_info, client, unit, speed, name): # noqa: F811
    # Get the mocked return value
    with open(join(TEST_DATA_DIR, 'get_devices.json')) as f:
        mock_get_devices.return_value = json.load(f)
    with open(join(TEST_DATA_DIR, 'get_device_10.json')) as f:
        dev10 = json.load(f)
        dev10['FanSpeed'] = name        # it should be set to this name
        mock_get_device_info.return_value = dev10

    # Send the /set_speed
    response = client.post(
        "/api/v1/set_speed",
        json={"unit": unit, "speed": speed}
    )
    assert response.status_code == 200  # Check for successful HTTP status
    response_json = response.json
    assert response_json["status"] == "ok"
    assert response_json["unit"] == unit
    assert response_json["speed"] == speed
    assert 'device_name' in response_json
    device_name = response_json['device_name']

    # Verify that these were both called with the arguments
    mock_get_devices.assert_called_once_with()
    mock_get_device_info.assert_called_once_with(unit)
    mock_set_fan_speed.assert_called_once_with(unit, speed)

    # Verify that the database got updated
    # Note that we are using the TEST_DB_NAME put in the environment.
    with sqlite3.connect(os.environ['TEST_DB_NAME']) as test_conn_verify:
        test_conn_verify.row_factory = sqlite3.Row
        cursor = test_conn_verify.cursor()
        cursor.execute("SELECT ipaddr, unit, new_value, agent FROM changelog WHERE unit = ? AND new_value = ?;",
                       (unit, str(speed)))
        changelog_entry = cursor.fetchone()

        assert changelog_entry is not None
        assert changelog_entry['ipaddr'] == '127.0.0.1'  # Flask test client IP
        assert changelog_entry['unit'] == unit
        assert changelog_entry['new_value'] == str(speed)
        assert changelog_entry['agent'] == 'web'

        cursor.execute("SELECT * from devices where device_name=?", (device_name,))
        row = cursor.fetchone()
        logging.debug("row=%s", dict(row))
        device_id = row['device_id']
        cursor.execute("SELECT * from devlog where device_id=? order by logtime desc", (device_id,))
        row = cursor.fetchone()
        extracted_status = ae200.extract_status(json.loads(row['status_json']))
        assert extracted_status['drive_speed_val'] == speed

    logging.info("/set_speed (unit=%s, speed=%s):", unit, speed)
