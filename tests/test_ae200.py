"""
Integration tests for AE200 device communication.
"""
import asyncio
import concurrent.futures
import socket
import stat
import threading

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


def test_extract_set_temperatures_promotes_auto_dual_setpoints():
    """AE-200 dual-setpoint Auto values should be convenient at the API boundary."""
    status = {
        "SetTemp": "24",
        "SetTemp1": "25",
        "SetTemp2": "19",
        "AutoMin": "18",
        "AutoMax": "27",
    }
    extracted = ae200.extract_set_temperatures(status)
    assert extracted == {
        "set_temp_c": 24.0,
        "cool_set_temp_c": 25.0,
        "heat_set_temp_c": 19.0,
        "auto_min_c": 18.0,
        "auto_max_c": 27.0,
    }


async def _async_value(value):
    return value


async def _record_active_command(state):
    with state["lock"]:
        state["active"] += 1
        state["max_active"] = max(state["max_active"], state["active"])
    await asyncio.sleep(0.05)
    with state["lock"]:
        state["active"] -= 1
    return "ok"


def test_async_runner_runs_without_current_event_loop(monkeypatch, tmp_path):
    """Synchronous AE-200 callers should get a fresh event loop per request."""
    monkeypatch.setattr(ae200, "AE200_COMMAND_LOCK_PATH", str(tmp_path / "ae200.lock"))
    assert ae200.AsyncRunner().run_async_safely(_async_value("ok")) == "ok"


def test_async_runner_runs_inside_current_event_loop(monkeypatch, tmp_path):
    """Async callers should not reuse or nest the currently running loop."""
    monkeypatch.setattr(ae200, "AE200_COMMAND_LOCK_PATH", str(tmp_path / "ae200.lock"))

    async def call_runner():
        return ae200.AsyncRunner().run_async_safely(_async_value("ok"))

    assert asyncio.run(call_runner()) == "ok"


def test_ae200_command_lock_is_reusable_without_write_permission(monkeypatch, tmp_path):
    """Separate service accounts must be able to open an existing shared lock."""
    lock_path = tmp_path / "ae200.lock"
    monkeypatch.setattr(ae200, "AE200_COMMAND_LOCK_PATH", str(lock_path))

    with ae200.ae200_command_lock():
        pass

    assert stat.S_IMODE(lock_path.stat().st_mode) == ae200.AE200_COMMAND_LOCK_MODE
    with ae200.ae200_command_lock():
        pass


def test_ae200_command_lock_defaults_to_managed_runtime_path():
    assert ae200.AE200_COMMAND_LOCK_PATH == "/run/lock/temperature-bot/ae200.lock"


def test_async_runner_serializes_commands(monkeypatch, tmp_path):
    """AE-200 commands should not run concurrently through one runner."""
    monkeypatch.setattr(ae200, "AE200_COMMAND_LOCK_PATH", str(tmp_path / "ae200.lock"))
    runner = ae200.AsyncRunner()
    state = {"active": 0, "max_active": 0, "lock": threading.Lock()}
    start_barrier = threading.Barrier(2)

    def run_command():
        start_barrier.wait(timeout=1)
        return runner.run_async_safely(_record_active_command(state))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run_command) for _ in range(2)]
        results = [future.result(timeout=2) for future in futures]

    assert results == ["ok", "ok"]
    assert state["max_active"] == 1


def test_set_mode_updates_simulator_and_rejects_unknown():
    """The AE-200 simulator should reflect commanded operation modes."""
    device_id = 10
    original_mode = ae200.get_device_info(device_id).get(ae200.AE200_MODE_KEY)
    try:
        ae200.set_mode(device_id, "DRY")
        assert ae200.get_device_info(device_id)[ae200.AE200_MODE_KEY] == "DRY"
        with pytest.raises(ValueError):
            ae200.set_mode(device_id, "SETBACK")
    finally:
        if original_mode in ae200.AE200_ALLOWED_SET_MODES:
            ae200.set_mode(device_id, original_mode)
