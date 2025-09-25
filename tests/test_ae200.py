"""
Integration tests for AE200 device communication.
"""
import socket
import pytest
from app import ae200
from app.util import get_config

def can_connect_to_ae200():
    """Checks if the AE200 device is reachable for integration testing.
    Uses configured host to avoid false negatives.
    """
    try:
        host = get_config().get('ae200', {}).get('host', '127.0.0.1')
        port = 80  # Adjust if AE200 uses a different port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.2)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except (socket.error, OSError):
        return False

@pytest.mark.skipif(
    not can_connect_to_ae200(),
    reason="AE200 device not reachable"
)
def test_ae200_subprocess_get_devices():
    devices = ae200.get_devices()
    assert isinstance(devices, list)
    assert len(devices) > 0
    for device in devices:
        assert "id" in device
        assert "name" in device
