"""
Rules for BasisTech HVAC robot.
"""
# ruff: noqa
# pylint: disable=global-statement, invalid-name, missing-function-docstring, unused-variable, undefined-variable, name-defined

DEFAULT_ERV_SPEED = 1
kitchen_erv_speed = DEFAULT_ERV_SPEED
restrooms_erv_speed = DEFAULT_ERV_SPEED

# AQI > 100 is unhealthy for sensitive groups
# AQI > 150 is unhealthy

if TUESDAY or THURSDAY:
    if HOUR in [11, 12]:
        kitchen_erv_speed = 4

if AQI>100:
    kitchen_erv_speed = 1
    restrooms_erv_speed = 1

if AQI>150:
    kitchen_erv_speed = 0
    restrooms_erv_speed = 0


if kitchen_erv_speed==0:
    set_drive(ERV_KITCHEN,0)
else:
    set_drive(ERV_KITCHEN,1)
    set_fan_speed(ERV_KITCHEN,kitchen_erv_speed)

if restrooms_erv_speed==0:
    set_drive(ERV_RESTROOMS,0)
else:
    set_drive(ERV_RESTROOMS,1)
    set_fan_speed(ERV_RESTROOMS,restrooms_erv_speed)
