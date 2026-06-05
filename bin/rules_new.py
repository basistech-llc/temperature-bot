"""
Rules for BasisTech HVAC robot.
Edit this file to change the rules!
This file is rules.py that gets evaluated by the rules engine.
When it is evaluated, all of the devices are defined as upper-case constants.
"""
# ruff: noqa
# pylint: disable=global-statement, invalid-name, missing-function-docstring, unused-variable, undefined-variable, name-defined

from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, Field, StringConstraints

class Device(BaseModel):
    erv: bool = Field(description="is this an ERV?")
    name: str = Field(description="the name of the device")

class RuleResult(BaseModel):
    fan_speed: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True)] | None
    drive: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True)] | None

DEFAULT_KITCHEN_ERV_SPEED = 2
DEFAULT_RESTROOMS_ERV_SPEED = 4

# weekdays
MONDAY = 0
TUESDAY = 1
WEDNESDAY = 2
THURSDAY = 3
FRIDAY = 4
SATURDAY = 5
SUNDAY = 6

def run_rules(device:Device, now:datetime, aqi:AQI):RuleResult
    # AQI rules:
    # AQI>50 is yellow - moderate
    # AQI>100 is orange - unhealthy for sensitive groups
    if device.erv:
        if aqi>100:
            return RuleResult(fan_speed="Low", drive="on")

        if aqi>50:
            return RuleResult(drive="off")


        # Turn on kitchen fan for cooking
        if ((now.weekday() in (TUESDAY, THURSDAY))  and
            (now.hour in [11, 12]) and
            ('kitchen' in device.name.lower())):
            return RuleResult(fan_speed="High", drive="on")

        #
        # By default, from 10pm to 5am every day, put the kitchen and restroom ERVs
        # on full speed to clear out the air.

        if now.hour in [22, 23, 0, 1, 2, 3, 4, 5]:
            return RuleResult(fan_speed="High", drive="on")
