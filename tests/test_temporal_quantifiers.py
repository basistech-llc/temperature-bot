"""
Test temporal quantifiers for logs and device_log endpoints
"""
import time
import os
import pytest

from app import db

def test_logs_endpoint_with_start(flask_test_client): # noqa: F811
    """Test /api/v1/logs with start parameter"""
    start_time = int(time.time()) - 86400  # 24 hours ago
    response = flask_test_client.get(f"/api/v1/logs?start={start_time}")
    assert response.status_code == 200
    data = response.json
    assert "data" in data
    assert "recordsTotal" in data


def test_logs_endpoint_with_end(flask_test_client): # noqa: F811
    """Test /api/v1/logs with end parameter"""
    end_time = int(time.time())
    response = flask_test_client.get(f"/api/v1/logs?end={end_time}")
    assert response.status_code == 200
    data = response.json
    assert "data" in data
    assert "recordsTotal" in data


def test_logs_endpoint_with_start_and_end(flask_test_client): # noqa: F811
    """Test /api/v1/logs with both start and end parameters"""
    start_time = int(time.time()) - 86400  # 24 hours ago
    end_time = int(time.time())
    response = flask_test_client.get(f"/api/v1/logs?start={start_time}&end={end_time}")
    assert response.status_code == 200
    data = response.json
    assert "data" in data
    assert "recordsTotal" in data


def test_device_log_endpoint_with_start(flask_test_client): # noqa: F811
    """Test /device_log/{device_id} with start parameter"""
    # Create a test device
    test_conn = db.connect_db(os.environ['TEST_DB_NAME'])
    cursor = test_conn.cursor()
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Test Device",))
    device_id = cursor.lastrowid
    test_conn.commit()
    test_conn.close()

    start_time = int(time.time()) - 86400  # 24 hours ago
    response = flask_test_client.get(f"/device_log/{device_id}?start={start_time}")
    assert response.status_code == 200
    assert "Test Device" in response.data.decode('utf-8')

def test_device_log_endpoint_with_end(flask_test_client): # noqa: F811
    """Test /device_log/{device_id} with end parameter"""

    # Create a test device
    test_conn = db.connect_db(os.environ['TEST_DB_NAME'])
    cursor = test_conn.cursor()
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Test Device 2",))
    device_id = cursor.lastrowid
    test_conn.commit()
    test_conn.close()

    end_time = int(time.time())
    response = flask_test_client.get(f"/device_log/{device_id}?end={end_time}")
    assert response.status_code == 200
    assert "Test Device 2" in response.data.decode('utf-8')


def test_device_log_endpoint_with_start_and_end(flask_test_client): # noqa: F811
    """Test /device_log/{device_id} with both start and end parameters"""
    # Create a test device
    test_conn = db.connect_db(os.environ['TEST_DB_NAME'])
    cursor = test_conn.cursor()
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Test Device 3",))
    device_id = cursor.lastrowid
    test_conn.commit()
    test_conn.close()

    start_time = int(time.time()) - 86400  # 24 hours ago
    end_time = int(time.time())
    response = flask_test_client.get(f"/device_log/{device_id}?start={start_time}&end={end_time}")
    assert response.status_code == 200
    assert "Test Device 3" in response.data.decode('utf-8')


@pytest.fixture
def test_temporal_links_in_template(flask_test_client):  # noqa: F811
    """Test that temporal links are generated correctly in the template"""
    device_id = 0
    response = flask_test_client.get("/")
    assert response.status_code == 200
    content = response.data.decode('utf-8')
    # Check that the device name and temporal links are present
    assert "Fixture Device" in content
    assert "day" in content
    assert "week" in content
    assert "all" in content
    # Check that the links have the correct format
    assert f"/device_log/{device_id}?start=" in content
    assert f"/device_log/{device_id}?start=" in content
    assert f"/device_log/{device_id}\" target=\"_blank\">all" in content


def test_temperature_api_with_device_id(flask_test_client, test_database_conn_with_test_data): # noqa: F811
    """Test /api/v1/temperature with device_id parameter"""
    device_id = test_database_conn_with_test_data[1]
    response = flask_test_client.get(f"/api/v1/temperature?device_id={device_id}")
    assert response.status_code == 200
    data = response.json
    assert "series" in data
    # Should return data for the specific device


def test_temperature_api_with_start_and_end(flask_test_client, test_database_conn_with_test_data): # noqa: F811
    """Test /api/v1/temperature with start and end parameters"""
    device_id = test_database_conn_with_test_data[1]
    start_time = int(time.time()) - 86400  # 24 hours ago
    end_time = int(time.time())
    response = flask_test_client.get(f"/api/v1/temperature?device_id={device_id}&start={start_time}&end={end_time}")
    assert response.status_code == 200
    data = response.json
    assert "series" in data


def test_chart_page_with_device_id(flask_test_client, test_database_conn_with_test_data): # noqa: F811
    """Test /chart page with device_id parameter"""
    device_id = test_database_conn_with_test_data[1]
    response = flask_test_client.get(f"/chart?device_id={device_id}")
    assert response.status_code == 200
    content = response.data.decode('utf-8')
    assert "Temperature Time Series" in content
    assert "day" in content
    assert "week" in content
    assert "month" in content


def test_index_layout_and_sections(flask_test_client):  # noqa: F811
    """Index page should show split ERV/FCU sections and Air Quality."""
    response = flask_test_client.get("/")
    assert response.status_code == 200
    content = response.data.decode("utf-8")
    assert "Heating and Cooling" in content
    assert "Ventilation (ERVs)" in content
    assert "Rooms (FCUs)" in content
    assert "Air Quality" in content


def test_index_fcu_speeds_exclude_one(flask_test_client, test_database_conn_with_test_data):  # noqa: F811
    """FCU rows expose Off, Auto, 2/3/4 speeds but not 1."""
    _, device_id, _ = test_database_conn_with_test_data
    response = flask_test_client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    # Off and Auto should be present
    assert f'id="radio-{device_id}-0"' in html
    assert f'id="radio-{device_id}-auto"' in html

    # Speeds 2, 3, 4 should be present
    for speed in (2, 3, 4):
        assert f'id="radio-{device_id}-{speed}"' in html

    # Speed 1 should not be present for this FCU
    assert f'id="radio-{device_id}-1"' not in html
