"""
test_chart_functionality.py
"""
import json
import logging

logger = logging.getLogger(__name__)

def test_status_api_endpoint_for_devices(flask_test_client):  # noqa: F811 # pylint: disable=unused-argument
    """Test that the /api/v1/status endpoint returns all devices"""
    response = flask_test_client.get('/api/v1/status')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert 'devices' in data
    assert isinstance(data['devices'], list)

    # Check that each device has required fields
    for device in data['devices']:
        assert 'device_id' in device
        assert 'device_name' in device
        assert isinstance(device['device_id'], int)
        assert isinstance(device['device_name'], str)

def test_chart_page_with_specific_devices(flask_test_client): # noqa: F811 # pylint: disable=unused-argument
    """Test that the chart page loads with specific devices"""
    response = flask_test_client.get('/chart?device_ids=1,2')
    assert response.status_code == 200

    content = response.data.decode('utf-8')
    # Should test this
    logger.info("content=%s",content)


def test_temperature_api_with_multiple_devices(flask_test_client): # noqa: F811 # pylint: disable=unused-argument
    """Test that the temperature API works with multiple device IDs"""
    response = flask_test_client.get('/api/v1/temperature?device_ids=1,2')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert 'series' in data
    assert isinstance(data['series'], list)
