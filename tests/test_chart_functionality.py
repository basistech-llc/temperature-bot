"""
test_chart_functionality.py
"""

import json
import logging

logger = logging.getLogger(__name__)


def test_status_api_endpoint_for_devices(flask_test_client):  # noqa: F811 # pylint: disable=unused-argument
    """Test that the /api/v1/status endpoint returns all devices"""
    response = flask_test_client.get("/api/v1/status")
    assert response.status_code == 200

    data = json.loads(response.data)
    assert "devices" in data
    assert isinstance(data["devices"], list)

    # Check that each device has required fields
    for device in data["devices"]:
        assert "device_id" in device
        assert "device_name" in device
        assert isinstance(device["device_id"], int)
        assert isinstance(device["device_name"], str)


def test_chart_page_with_specific_devices(flask_test_client):  # noqa: F811 # pylint: disable=unused-argument
    """Test that the chart page loads with specific devices"""
    response = flask_test_client.get("/chart?device_ids=1,2")
    assert response.status_code == 200

    content = response.data.decode("utf-8")
    logger.info("content=%s...", content[:50])


def test_temperature_chart_page_has_exclusion_controls(flask_test_client):  # noqa: F811
    """Temperature chart page has Select All / Clear All and temperature_chart_support.js for exclusion-set behavior."""
    response = flask_test_client.get("/chart")
    assert response.status_code == 200
    content = response.data.decode("utf-8")
    assert "Select All" in content
    assert "Clear All" in content
    assert "temperature_chart_support.js" in content
    assert 'id="checkboxes"' in content
    assert 'id="temp-chart"' in content
    assert 'id="earlierDataBtn"' in content
    assert 'id="laterDataBtn"' in content


def test_chart_aqi_page_loads(flask_test_client):  # noqa: F811
    """Air Quality Chart page loads with AQI chart and temporal controls."""
    response = flask_test_client.get("/chart_aqi")
    assert response.status_code == 200
    content = response.data.decode("utf-8")
    assert "Air Quality Chart" in content
    assert 'id="aqi-chart"' in content
    assert "chart_aqi_support.js" in content
    assert "day" in content
    assert "week" in content
    assert "month" in content
    assert "all" in content


def test_lighting_chart_page_loads(flask_test_client):  # noqa: F811
    """Lighting chart page loads with lighting chart and temporal controls."""
    response = flask_test_client.get("/lighting_chart")
    assert response.status_code == 200
    content = response.data.decode("utf-8")
    assert "Lighting Time Series" in content
    assert 'id="lighting-chart"' in content
    assert "lighting_chart_support.js" in content
    assert "day" in content
    assert "week" in content
    assert "month" in content
    assert "all" in content


def test_temperature_api_with_multiple_devices(flask_test_client):  # noqa: F811 # pylint: disable=unused-argument
    """Temperature API returns series with device_id, name, and data for chart keying by device."""
    response = flask_test_client.get("/api/v1/temperature?device_ids=1,2")
    assert response.status_code == 200

    data = json.loads(response.data)
    assert "series" in data
    assert isinstance(data["series"], list)
    for s in data["series"]:
        assert "device_id" in s, "each series must include device_id for chart keying"
        assert "name" in s
        assert "data" in s
        assert isinstance(s["data"], list)


def test_status_api_devices_sorted_alphabetically(flask_test_client):  # noqa: F811 # pylint: disable=unused-argument
    """Test that devices in the /api/v1/status endpoint are sorted alphabetically"""
    response = flask_test_client.get("/api/v1/status")
    assert response.status_code == 200

    data = json.loads(response.data)
    assert "devices" in data
    device_names = [device["device_name"] for device in data["devices"]]
    # Check that device names are sorted alphabetically
    sorted_device_names = sorted(device_names)
    assert device_names == sorted_device_names, (
        f"Devices are not sorted alphabetically. Got: {device_names}, Expected: {sorted_device_names}"
    )
