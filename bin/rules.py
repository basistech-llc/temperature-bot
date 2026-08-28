"""
Rules for BasisTech HVAC robot.
Edit this file to change the rules!
This file is loaded by the rules engine and defines action and alert rules.
"""
# ruff: noqa
# pylint: disable=global-statement, invalid-name, missing-function-docstring, unused-variable, undefined-variable, name-defined

from datetime import datetime

from app.device_types import DEVICE_SUBTYPE_AIRTHINGS
from app.models import (
    AlertRuleDevice,
    AlertRuleResult,
    AlertRuleState,
    Device,
    RuleResult,
    THURSDAY,
    TUESDAY,
)


AIRTHINGS_STUCK_SECONDS = 10 * 60
ALERT_RULE_HISTORY_SECONDS = AIRTHINGS_STUCK_SECONDS
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
    if device.device_subtype != DEVICE_SUBTYPE_AIRTHINGS:
        return []

    display_name = device.name.removeprefix("Airthings ")
    state = AlertRuleState.INDETERMINATE
    reason = device.input_error
    if device.status is not None and not AIRTHINGS_SENSOR_FIELDS.issubset(
        device.status.model_dump()
    ):
        reason = "one or more required measurements are missing"
    elif (
        device.reading_age_seconds is not None
        and device.reading_age_seconds > AIRTHINGS_READING_FRESH_SECONDS
    ):
        reason = (
            f"the latest reading is {_duration_label(device.reading_age_seconds)} old"
        )
    elif device.unchanged_for_seconds is not None:
        state = (
            AlertRuleState.ACTIVE
            if device.unchanged_for_seconds >= AIRTHINGS_STUCK_SECONDS
            else AlertRuleState.INACTIVE
        )

    unchanged = _duration_label(device.unchanged_for_seconds or 0)
    if state == AlertRuleState.INDETERMINATE:
        message = (
            f":warning: Airthings {display_name} sensor-stuck alert remains active, "
            f"but it cannot be evaluated: {reason or 'the input is indeterminate'}."
        )
    else:
        message = (
            f":warning: Airthings {display_name} is stuck: all reported "
            f"measurements have been exactly unchanged for {unchanged}."
        )
    return [
        AlertRuleResult(
            alert_type="SensorStuck",
            state=state,
            started_at=device.unchanged_since,
            message=message,
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
