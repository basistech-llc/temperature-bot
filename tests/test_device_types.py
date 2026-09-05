"""Tests for discovery-driven device classification."""

import json
from pathlib import Path

from app.device_types import (
    HubitatControlDevice,
    HubitatDevice,
    classify_hubitat_device,
    classify_legacy_hubitat_name,
)


def _device(*, capabilities=(), commands=()) -> HubitatDevice:
    return HubitatDevice.model_validate(
        {
            "name": "test",
            "capabilities": list(capabilities),
            "commands": [{"command": command} for command in commands],
        }
    )


def test_hubitat_fan_precedes_generic_control():
    device_type, _ = classify_hubitat_device(
        _device(capabilities={"FanControl", "Actuator", "Switch"})
    )
    assert device_type == "FAN"


def test_hubitat_control_precedes_sensor():
    device_type, _ = classify_hubitat_device(
        _device(capabilities={"Actuator", "Switch", "TemperatureMeasurement"})
    )
    assert device_type == "CONTROL"


def test_hubitat_sensor_capability():
    device_type, _ = classify_hubitat_device(
        _device(capabilities={"TemperatureMeasurement", "Sensor"})
    )
    assert device_type == "SENSOR"


def test_hubitat_control_command_fallback():
    device_type, _ = classify_hubitat_device(_device(commands={"setLevel"}))
    assert device_type == "CONTROL"


def test_legacy_hubitat_names_are_only_a_backfill_fallback():
    assert classify_legacy_hubitat_name("A51 Dimmer #1")[0] == "CONTROL"
    assert classify_legacy_hubitat_name("Dungeon Meter")[0] == "SENSOR"
    assert classify_legacy_hubitat_name("Unrecognized Device")[0] == "CONTROL"


def test_unrecognized_hubitat_device_defaults_to_control():
    assert classify_hubitat_device(_device())[0] == "CONTROL"


def test_control_attributes_accept_the_live_single_device_shape():
    """Maker API returns two attribute shapes and only one was accepted.

    ``/devices/all`` sends a mapping, but ``/devices/<id>`` -- the endpoint room
    control status actually calls -- sends a list of records. Rejecting the list
    made every live control read fail validation, so Hickory's controls reported
    unreadable in production and Broadway's would have too. The payloads here
    were captured from the production hub.
    """
    payloads = json.loads(
        (Path(__file__).resolve().parents[1] / "app/test_data/hubitat_control_devices.json")
        .read_text(encoding="utf-8")
    )

    switch = HubitatControlDevice.model_validate(payloads["switch"])
    assert switch.attributes.switch == "on"

    # A fan carries speed and level alongside switch; its speed vocabulary is
    # wider than the four speeds we offer, so it must survive untouched.
    fan = HubitatControlDevice.model_validate(payloads["fan"])
    assert fan.attributes.switch == "on"
    assert fan.attributes.speed == "high"
    assert fan.attributes.level == 98

    # The Hue group lists switch and colorName twice; last entry wins.
    dimmer = HubitatControlDevice.model_validate(payloads["dimmer"])
    assert dimmer.attributes.switch == "on"
    assert dimmer.attributes.level == 70


def test_control_attributes_still_accept_the_mapping_shape():
    """The /devices/all mapping shape must keep working alongside the list."""
    device = HubitatControlDevice.model_validate(
        {"attributes": {"switch": "off", "level": "42", "speed": "medium-low"}}
    )
    assert device.attributes.switch == "off"
    assert device.attributes.level == 42
    assert device.attributes.speed == "medium-low"


def test_control_attributes_tolerate_junk_entries():
    """A malformed entry must not lose the rest of a device's state."""
    device = HubitatControlDevice.model_validate(
        {"attributes": [{"name": "switch", "currentValue": "on"}, "junk", {"noname": 1}]}
    )
    assert device.attributes.switch == "on"


def test_duplicate_attribute_prefers_the_last_reported_value():
    """A trailing null must not erase a real reading from an earlier duplicate.

    The Hue group driver lists switch twice. Both entries agree today, so
    last-wins looked harmless, but a null in the later slot would have shown a
    lit group as unknown.
    """
    device = HubitatControlDevice.model_validate(
        {
            "attributes": [
                {"name": "switch", "currentValue": "on"},
                {"name": "switch", "currentValue": None},
            ]
        }
    )
    assert device.attributes.switch == "on"

    # A later real value still supersedes an earlier one.
    superseded = HubitatControlDevice.model_validate(
        {
            "attributes": [
                {"name": "switch", "currentValue": "on"},
                {"name": "switch", "currentValue": "off"},
            ]
        }
    )
    assert superseded.attributes.switch == "off"
