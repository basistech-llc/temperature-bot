"""
Rules for BasisTech HVAC robot.
"""
# ruff: noqa
# pylint: disable=global-statement, invalid-name, missing-function-docstring, unused-variable, undefined-variable

if TUESDAY or THURSDAY:
    if HOUR==11:
        set_fan(ERV_KITCHEN, 4)
    if HOUR==13:
        set_fan(ERV_KITCHEN, 1)
