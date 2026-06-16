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


# -- friendly_fan_speed_label unit tests --
#
# These guard the alerts table (and any other button-less surface) against
# showing the raw AE200 protocol code (e.g. 'MID1') to users, which is the
# regression that prompted hvac-hml. The same speed code must resolve to a
# different label depending on device type, so each path is covered.


def test_friendly_fan_speed_label_erv_uses_erv_vocabulary():
    """ERVs expose four levels; MID2/MID1 must read MED-LO/MED-HI, not the
    plain-fan LO/MED, so the label matches the ERV's own control buttons."""
    assert ae200.friendly_fan_speed_label("ERV Restrooms", "HIGH") == "HI"
    assert ae200.friendly_fan_speed_label("ERV Restrooms", "MID2") == "MED-LO"
    assert ae200.friendly_fan_speed_label("ERV Restrooms", "MID1") == "MED-HI"
    assert ae200.friendly_fan_speed_label("ERV Restrooms", "LOW") == "LO"


def test_friendly_fan_speed_label_fan_uses_fan_vocabulary():
    """Plain fans collapse the middle levels: the same MID2/MID1 codes read
    LO/MED here, matching the fan's three-speed button set."""
    assert ae200.friendly_fan_speed_label("Restrooms/BOH", "HIGH") == "HI"
    assert ae200.friendly_fan_speed_label("Restrooms/BOH", "MID2") == "LO"
    assert ae200.friendly_fan_speed_label("Restrooms/BOH", "MID1") == "MED"


def test_friendly_fan_speed_label_auto():
    """AUTO maps to 'Auto' for both device types."""
    assert ae200.friendly_fan_speed_label("ERV Restrooms", "AUTO") == "Auto"
    assert ae200.friendly_fan_speed_label("Restrooms/BOH", "AUTO") == "Auto"


def test_friendly_fan_speed_label_accepts_numeric_speed():
    """Callers may pass the speed number rather than the protocol string."""
    assert ae200.friendly_fan_speed_label("ERV Restrooms", 4) == "HI"


def test_friendly_fan_speed_label_unknown_and_none():
    """Unrecognized values pass through unchanged (never hide diagnostics);
    None stays None so callers can distinguish 'no data'."""
    assert ae200.friendly_fan_speed_label("ERV Restrooms", "BOGUS") == "BOGUS"
    assert ae200.friendly_fan_speed_label("Restrooms/BOH", None) is None


def test_extract_drive_and_fan_speed_promotes_mode():
    """AE-200 Mode should be convenient at the JSON API boundary."""
    status = {"Drive": "ON", "FanSpeed": "LOW", "Mode": "COOL"}
    extracted = ae200.extract_drive_and_fan_speed(status)
    assert extracted["mode"] == "COOL"
    assert extracted["drive"] == 1
    assert extracted["fan_speed"] == 1
    assert extracted["has_speed_control"] is True


def test_extract_drive_and_fan_speed_keeps_mode_without_speed_control():
    """Mode is useful diagnostic data even when speed control is absent."""
    extracted = ae200.extract_drive_and_fan_speed({"Mode": "HEAT"})
    assert extracted == {"mode": "HEAT", "has_speed_control": False}


def test_set_mode_updates_simulator_and_rejects_unknown():
    """The AE-200 simulator should reflect commanded operation modes."""
    device_id = 10
    original_mode = ae200.get_device_info(device_id).get(ae200.AE200_MODE_KEY)
    try:
        ae200.set_mode(device_id, "HEAT")
        assert ae200.get_device_info(device_id)[ae200.AE200_MODE_KEY] == "HEAT"
        with pytest.raises(ValueError):
            ae200.set_mode(device_id, "AUTO")
    finally:
        if original_mode in ae200.AE200_ALLOWED_SET_MODES:
            ae200.set_mode(device_id, original_mode)
