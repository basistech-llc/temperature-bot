import pytest
from app.main import app
import json

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_status_api_endpoint_for_devices(client):
    """Test that the /api/v1/status endpoint returns all devices"""
    response = client.get('/api/v1/status')
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

def test_chart_page_with_device_dropdown(client):
    """Test that the chart page loads with device dropdown"""
    response = client.get('/chart')
    assert response.status_code == 200

    # Check that the dropdown HTML is present
    content = response.data.decode('utf-8')
    assert 'Add device:' in content
    assert 'addDeviceSelect' in content
    assert 'Select a device...' in content

def test_chart_page_with_specific_devices(client):
    """Test that the chart page loads with specific devices"""
    response = client.get('/chart?device_ids=1,2')
    assert response.status_code == 200

    content = response.data.decode('utf-8')
    assert 'currentDeviceIds' in content
    # Should contain the device IDs in the JavaScript
    assert '[1, 2]' in content or '1,2' in content

def test_temperature_api_with_multiple_devices(client):
    """Test that the temperature API works with multiple device IDs"""
    response = client.get('/api/v1/temperature?device_ids=1,2')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert 'series' in data
    assert isinstance(data['series'], list)