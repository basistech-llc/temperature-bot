"""Tests for discovery-driven device classification."""

from app.device_types import (
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
