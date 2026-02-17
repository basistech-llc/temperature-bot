"""
Rules for BasisTech HVAC robot.
Edit this file to change the rules!
"""
# ruff: noqa
# pylint: disable=global-statement, invalid-name, missing-function-docstring, unused-variable, undefined-variable, name-defined

DEFAULT_KITCHEN_ERV_SPEED = 2
DEFAULT_RESTROOMS_ERV_SPEED = 4

kitchen_erv_speed = DEFAULT_KITCHEN_ERV_SPEED
restrooms_erv_speed = DEFAULT_RESTROOMS_ERV_SPEED

# AQI > 100 is unhealthy for sensitive groups
# AQI > 150 is unhealthy

if TUESDAY or THURSDAY:
    if HOUR in [11, 12]:
        kitchen_erv_speed = 4

if HOUR in [22, 23, 0, 1, 2, 3, 4, 5]:
    kitchen_erv_speed = 4


# AQI>50 is yellow - moderate
if AQI>50:
    kitchen_erv_speed = 1
    restrooms_erv_speed = 1

# AQI>100 is orange - unhealthy for sensitive groups
if AQI>100:
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
