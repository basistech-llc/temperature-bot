"""
Rules for BasisTech HVAC robot.
"""
# ruff: noqa
# pylint: disable=global-statement, invalid-name, missing-function-docstring, unused-variable, undefined-variable, name-defined

DEFAULT_ERV_SPEED = 1
kitchen_erv_speed = DEFAULT_ERV_SPEED
restrooms_erv_speed = DEFAULT_ERV_SPEED


if TUESDAY or THURSDAY:
    if HOUR in [11, 12]:
        kitchen_erv_speed = 4

if AQI>100:
    kitchen_erv_speed = 0
    restrooms_erv_speed = 0

set_fan(ERV_KITCHEN,kitchen_erv_speed)
set_fan(ERV_RESTROOMS,restrooms_erv_speed)
