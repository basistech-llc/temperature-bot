"""
Rules for BasisTech HVAC robot.
Edit this file to change the rules!
This file is loaded by the rules engine and must define run_rules_for_device().
"""
# ruff: noqa
# pylint: disable=global-statement, invalid-name, missing-function-docstring, unused-variable, undefined-variable, name-defined

from datetime import datetime

from app.models import Device, RuleResult, THURSDAY, TUESDAY


def run_rules_for_device(device: Device, now: datetime, aqi: int) -> RuleResult | None:
    # AQI rules:
    # AQI>50 is yellow - moderate
    # AQI>100 is orange - unhealthy for sensitive groups
    if device.erv:
        if aqi > 75:
            return RuleResult(drive="off")
        if aqi > 50:
            return RuleResult(fan_speed="Low", drive="on")


        # Turn on kitchen fan for cooking
        if (
            now.weekday() in (TUESDAY, THURSDAY)
            and now.hour in [11, 12]
            and "kitchen" in device.name.lower()
        ):
            return RuleResult(fan_speed="High", drive="on")

        # By default, from 10pm to 5am every day, put the kitchen and restroom ERVs
        # on full speed to clear out the air.
        if now.hour in [22, 23, 0, 1, 2, 3, 4, 5]:
            return RuleResult(fan_speed="High", drive="on")

    return None
