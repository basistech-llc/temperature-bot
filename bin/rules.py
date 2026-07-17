"""
Rules for BasisTech HVAC robot.
Edit this file to change the rules!
This file is loaded by the rules engine and defines action and alert rules.
"""
# ruff: noqa
# pylint: disable=global-statement, invalid-name, missing-function-docstring, unused-variable, undefined-variable, name-defined

from datetime import datetime

from app.models import (
    AlertRuleDevice,
    AlertRuleResult,
    Device,
    RuleResult,
    THURSDAY,
    TUESDAY,
)


AIRTHINGS_STUCK_SECONDS = 10 * 60
AIRTHINGS_READING_FRESH_SECONDS = 2 * 60
AIRTHINGS_SENSOR_FIELDS = frozenset(
    {
        "co2",
        "humidity",
        "pm1",
        "pm25",
        "pressure",
        "radonShortTermAvg",
        "temp",
        "voc",
    }
)


def _duration_label(seconds: int) -> str:
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''}"


def run_alert_rules_for_device(
    device: AlertRuleDevice, now: datetime
) -> list[AlertRuleResult]:
    """Return monitoring conditions; this function never changes equipment."""
    del now
    if not device.name.startswith("Airthings "):
        return []
    if device.reading_age_seconds > AIRTHINGS_READING_FRESH_SECONDS:
        return []
    if not AIRTHINGS_SENSOR_FIELDS.issubset(device.status.model_dump()):
        return []

    display_name = device.name.removeprefix("Airthings ")
    unchanged = _duration_label(device.unchanged_for_seconds)
    return [
        AlertRuleResult(
            alert_type="SensorStuck",
            active=device.unchanged_for_seconds >= AIRTHINGS_STUCK_SECONDS,
            started_at=device.unchanged_since,
            message=(
                f":warning: Airthings {display_name} is stuck: all reported "
                f"measurements have been exactly unchanged for {unchanged}."
            ),
            resolved_message=(
                f":white_check_mark: Airthings {display_name} is unstuck: "
                "reported measurements are changing again."
            ),
        )
    ]


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
