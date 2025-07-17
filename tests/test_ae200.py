import socket
import pytest
from app import ae200

def can_connect_to_ae200():
    try:
        host = "air.basistech.net"
        port = 80  # Adjust if AE200 uses a different port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.2)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
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