"""
Test temporal quantifiers for logs and device_log endpoints
"""
import time
import sqlite3
import os
import pytest
from fixtures import create_temporal_test_data,client # noqa: F401 # pylint: disable=unused-import


def test_logs_endpoint_with_start(client): # noqa: F811
    """Test /api/v1/logs with start parameter"""
    start_time = int(time.time()) - 86400  # 24 hours ago
    response = client.get(f"/api/v1/logs?start={start_time}")
    assert response.status_code == 200
    data = response.json
    assert "data" in data
    assert "recordsTotal" in data


def test_logs_endpoint_with_end(client): # noqa: F811
    """Test /api/v1/logs with end parameter"""
    end_time = int(time.time())
    response = client.get(f"/api/v1/logs?end={end_time}")
    assert response.status_code == 200
    data = response.json
    assert "data" in data
    assert "recordsTotal" in data


def test_logs_endpoint_with_start_and_end(client): # noqa: F811
    """Test /api/v1/logs with both start and end parameters"""
    start_time = int(time.time()) - 86400  # 24 hours ago
    end_time = int(time.time())
    response = client.get(f"/api/v1/logs?start={start_time}&end={end_time}")
    assert response.status_code == 200
    data = response.json
    assert "data" in data
    assert "recordsTotal" in data


def test_device_log_endpoint_with_start(client): # noqa: F811
    """Test /device_log/{device_id} with start parameter"""
    # Create a test device
    with sqlite3.connect(os.environ['TEST_DB_NAME']) as test_conn:
        test_conn.row_factory = sqlite3.Row
        cursor = test_conn.cursor()
        cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Test Device",))
        device_id = cursor.lastrowid
        test_conn.commit()

    start_time = int(time.time()) - 86400  # 24 hours ago
    response = client.get(f"/device_log/{device_id}?start={start_time}")
    assert response.status_code == 200
    assert "Test Device" in response.data.decode('utf-8')


def test_device_log_endpoint_with_end(client): # noqa: F811
    """Test /device_log/{device_id} with end parameter"""

    # Create a test device
    with sqlite3.connect(os.environ['TEST_DB_NAME']) as test_conn:
        test_conn.row_factory = sqlite3.Row
        cursor = test_conn.cursor()
        cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Test Device 2",))
        device_id = cursor.lastrowid
        test_conn.commit()

    end_time = int(time.time())
    response = client.get(f"/device_log/{device_id}?end={end_time}")
    assert response.status_code == 200
    assert "Test Device 2" in response.data.decode('utf-8')


def test_device_log_endpoint_with_start_and_end(client): # noqa: F811
    """Test /device_log/{device_id} with both start and end parameters"""
    # Create a test device
    with sqlite3.connect(os.environ['TEST_DB_NAME']) as test_conn:
        test_conn.row_factory = sqlite3.Row
        cursor = test_conn.cursor()
        cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Test Device 3",))
        device_id = cursor.lastrowid
        test_conn.commit()

    start_time = int(time.time()) - 86400  # 24 hours ago
    end_time = int(time.time())
    response = client.get(f"/device_log/{device_id}?start={start_time}&end={end_time}")
    assert response.status_code == 200
    assert "Test Device 3" in response.data.decode('utf-8')


@pytest.fixture
def device_in_db():
    # Create test device with temporal data
    with sqlite3.connect(os.environ['TEST_DB_NAME']) as test_conn:
        test_conn.row_factory = sqlite3.Row
        device_id, expected_counts = create_temporal_test_data(test_conn, "Fixture Device") # pylint: disable=unused-variable
        test_conn.commit()
    yield device_id

def test_temporal_links_in_template(client, device_in_db):  # noqa: F811
    """Test that temporal links are generated correctly in the template"""
    device_id = device_in_db
    response = client.get("/")
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


def test_temperature_api_with_device_id(client, device_in_db): # noqa: F811
    """Test /api/v1/temperature with device_id parameter"""
    device_id = device_in_db
    response = client.get(f"/api/v1/temperature?device_id={device_id}")
    assert response.status_code == 200
    data = response.json
    assert "series" in data
    # Should return data for the specific device


def test_temperature_api_with_start_and_end(client, device_in_db): # noqa: F811
    """Test /api/v1/temperature with start and end parameters"""
    device_id = device_in_db
    start_time = int(time.time()) - 86400  # 24 hours ago
    end_time = int(time.time())
    response = client.get(f"/api/v1/temperature?device_id={device_id}&start={start_time}&end={end_time}")
    assert response.status_code == 200
    data = response.json
    assert "series" in data


def test_chart_page_with_device_id(client, device_in_db): # noqa: F811
    """Test /chart page with device_id parameter"""
    device_id = device_in_db
    response = client.get(f"/chart?device_id={device_id}")
    assert response.status_code == 200
    content = response.data.decode('utf-8')
    assert "Temperature Time Series" in content
    assert "day" in content
    assert "week" in content
    assert "month" in content
