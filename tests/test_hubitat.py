"""
Tests for Hubitat integration helpers.
"""

import logging
from os.path import join
import json
from unittest.mock import patch

import pytest

from app import hubitat, room_config
from app.models import RoomControlKind
from app.paths import ETC_DIR
from bin import runner

logger = logging.getLogger(__name__)

HUBITAT_JSON = join(ETC_DIR, "sample_hubitat.json")


def _load_sample_devices():
    with open(HUBITAT_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_hubitat_extract_temperatures_numeric_fields():
    """extract_temperatures normalizes numeric attributes and exposes status payload."""
    hubdict = _load_sample_devices()
    temps = hubitat.extract_temperatures(hubdict)
    assert len(temps) == 15

    # Pick a representative device from the sample with known values.
    dungeon = next(t for t in temps if t["name"] == "Dungeon Meter")

    # Top-level temperature is a float, not a string.
    assert dungeon["temperature"] == pytest.approx(19.4)

    status = dungeon["status"]
    attrs = status["attributes"]

    # Status copies are numeric.
    assert status["temperature"] == pytest.approx(19.4)
    assert status["humidity"] == 15
    assert status["illuminance"] == 78

    # Attributes are also normalized to numbers where appropriate.
    assert attrs["temperature"] == pytest.approx(19.4)
    assert attrs["humidity"] == 15
    assert attrs["illuminance"] == 78


def test_hubitat_simulator_returns_checked_in_devices(monkeypatch):
    """Hubitat simulator mode should not require host/appId config."""
    monkeypatch.setenv(hubitat.HUBITAT_SIMULATOR_ENV, "1")
    devices = hubitat.get_all_devices()
    names = {device["name"] for device in devices}
    assert "Lobby Sensor on Somerville Broadway" in names
    assert "Hickory Sensor" in names
    assert "Dungeon Cage" in names


@patch("bin.runner.hubitat.get_all_devices")
def test_update_from_hubitat_persists_status_json(
    mock_get_all_devices, test_database_conn
):
    """update_from_hubitat writes both temp10x and rich status_json for Hubitat devices."""
    hubdict = _load_sample_devices()
    mock_get_all_devices.return_value = hubdict

    conn = test_database_conn

    # Run the updater against the test DB.
    runner.update_from_hubitat(conn)

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT d.device_name, l.temp10x, l.status_json
        FROM devices d
        JOIN devlog l ON d.device_id = l.device_id
        WHERE d.device_name = ?
        ORDER BY l.logtime DESC
        LIMIT 1
        """,
        ("Dungeon Meter",),
    )
    row = cursor.fetchone()
    assert row is not None

    # Temperature stored in temp10x matches the normalized value.
    assert row["temp10x"] == pytest.approx(194)  # 19.4 * 10

    status = json.loads(row["status_json"])
    # The persisted status carries numeric humidity and illuminance.
    assert status["name"] == "Dungeon Meter"
    assert status["temperature"] == pytest.approx(19.4)
    assert status["humidity"] == 15
    assert status["illuminance"] == 78

    discovered = cursor.execute(
        "SELECT device_name, device_type, room_id FROM devices ORDER BY device_name"
    ).fetchall()
    assert len(discovered) == len(hubdict)
    assert all(row["device_type"] is not None for row in discovered)
    assert all(row["room_id"] is None for row in discovered)
    expected_motion_observations = sum(
        (device.get("attributes") or {}).get("motion") in {"active", "inactive"}
        for device in hubdict
    )
    assert conn.execute("SELECT COUNT(*) FROM presence_events").fetchone()[0] == (
        expected_motion_observations
    )


def test_live_hubitat_commands_are_refused_from_tests():
    """The guard that keeps the suite off real hardware must itself be pinned.

    conftest's ``refuse_live_hubitat_commands`` is the only thing standing
    between an unpatched command test and a real office outlet, and it fails
    silently if ``send_device_command`` is renamed or the fixture stops
    applying. Calling through a wrapper rather than the low-level function
    proves the whole write layer is covered, not just the one name.

    The arguments are deliberately harmless. The regression this test detects
    is precisely the one where the call is not intercepted, so a real device id
    would make the test perform the write it exists to prevent. Hubitat ids are
    numeric, so this one can name nothing, and ``off`` could not energize it
    even if it did.
    """
    with pytest.raises(AssertionError, match="live Hubitat device not-a-device-id"):
        hubitat.set_switch("not-a-device-id", "off")


def test_simulator_carries_every_device_the_room_configs_address(monkeypatch):
    """A room control id must be checkable without reaching for the hub.

    The simulator snapshot held only temperature sensors, so no control id in
    ``room_config`` had any corroboration in the repo at all -- an id could be
    stale, from the wrong hub, or naming an unrelated device, and nothing here
    would contradict it. That is not theoretical: three Broadway controls
    shipped naming Kitchen and Cedar lights because their ids came off hub
    10.2.3.52.

    Every configured control is now captured from Maker API app 520. Asserting
    the capability rather than only the id is the point: an id that names
    something the control cannot drive fails here, which is exactly the shape
    of the wrong-hub mistake.
    """
    required_capability = {
        RoomControlKind.SWITCH: "Switch",
        RoomControlKind.DIMMER: "SwitchLevel",
        RoomControlKind.FAN: "FanControl",
    }
    monkeypatch.setenv(hubitat.HUBITAT_SIMULATOR_ENV, "1")
    devices = {device["id"]: device for device in hubitat.get_all_devices()}

    checked = 0
    for room_key, config in room_config.ROOM_CONFIGS.items():
        for control in config.controls:
            if control.device_id is None:
                continue
            where = f"{room_key}/{control.key}"
            assert control.device_id in devices, f"{where} names an unknown device"
            device = devices[control.device_id]
            assert required_capability[control.kind] in device["capabilities"], (
                f"{where} names {device['label']!r}, which is not a "
                f"{control.kind.value}"
            )
            checked += 1
    assert checked == 13


def test_simulator_can_resolve_the_tv_lift_by_label(monkeypatch):
    """The TV lift is addressed by label, not id, so ids alone do not cover it.

    ``control_room_tv`` looks its target up in the full device list, which means
    a renamed switch breaks the lift with no config change to notice. The
    labels only resolve offline if the simulator carries those devices too.
    """
    monkeypatch.setenv(hubitat.HUBITAT_SIMULATOR_ENV, "1")
    labels = {device["label"] for device in hubitat.get_all_devices()}
    hickory_tv = room_config.ROOM_CONFIGS["hickory"].find_control(
        "tv", RoomControlKind.TV
    )

    assert hickory_tv is not None
    assert hickory_tv.up_label in labels
    assert hickory_tv.down_label in labels
