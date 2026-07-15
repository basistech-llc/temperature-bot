"""Simulator environment flags require explicit true values."""

import pytest

from app import ae200, airquality, airthings, hubitat


SIMULATOR_FLAGS = (
    (ae200.ae200_simulator_enabled, ae200.AE200_SIMULATOR_ENV),
    (airthings.airthings_simulator_enabled, airthings.AIRTHINGS_SIMULATOR_ENV),
    (hubitat.hubitat_simulator_enabled, hubitat.HUBITAT_SIMULATOR_ENV),
    (airquality.aqicn_simulator_enabled, airquality.AQICN_SIMULATOR_ENV),
)


@pytest.mark.parametrize(("enabled", "env_name"), SIMULATOR_FLAGS)
@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
        (" On ", True),
        ("0", False),
        ("false", False),
        ("False", False),
        ("no", False),
        ("off", False),
        ("", False),
        ("random", False),
    ),
)
def test_simulator_flag_values(monkeypatch, value, expected, enabled, env_name):
    monkeypatch.setenv(env_name, value)
    assert enabled() is expected
