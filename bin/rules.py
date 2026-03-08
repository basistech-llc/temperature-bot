"""
Rules for BasisTech HVAC robot.
Edit this file to change the rules!
This file is rules.py that gets evaluated by the rules engine.
When it is evaluated, all of the devices are defined as upper-case constants.
"""
# ruff: noqa
# pylint: disable=global-statement, invalid-name, missing-function-docstring, unused-variable, undefined-variable, name-defined

DEFAULT_KITCHEN_ERV_SPEED = 2
DEFAULT_RESTROOMS_ERV_SPEED = 4

kitchen_erv_speed = DEFAULT_KITCHEN_ERV_SPEED
restrooms_erv_speed = DEFAULT_RESTROOMS_ERV_SPEED

# NOTE:
# AQI > 100 is unhealthy for sensitive groups
# AQI > 150 is unhealthy

if TUESDAY or THURSDAY:
    if HOUR in [11, 12]:
        kitchen_erv_speed = 4

#
# By default, from 10pm to 5am every day, put the kitchen and restroom ERVs
# on full speed to clear out the air.

if HOUR in [22, 23, 0, 1, 2, 3, 4, 5]:
    kitchen_erv_speed = 4
    restrooms_erv_speed = 4

#
# However, if the outdoor AQI is over 50, lower the ERV speed to 1
# And if it is over 100, lower it to 0

# AQI>50 is yellow - moderate
if AQI>50:
    kitchen_erv_speed = 1
    restrooms_erv_speed = 1

# AQI>100 is orange - unhealthy for sensitive groups
if AQI>100:
    kitchen_erv_speed = 0
    restrooms_erv_speed = 0

#
# If the ERV speed is 0, we actually have to turn off the drive
# Otherwise, we have to turn on the drive and set the speed.
#

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
