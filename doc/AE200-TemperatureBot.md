# AE-200 Operation Modes in TemperatureBot

This note documents how TemperatureBot handles AE-200 air-conditioner operation
modes. It is intended for readers who already know the AE-200 UI and need to
understand the narrower controls exposed by this application.

Sources:

- `doc/AE-200.pdf`, section "Operation mode", lists air-conditioner modes as
  Cool, Dry, Fan, Heat, Auto, and Setback.
- `doc/TechMan_AE-200.pdf`, group operation options, lists the same
  air-conditioner modes.
- `doc/AE-200.pdf`, section "Night Setback Control", describes Setback Control
  as automatic heating or cooling when a stopped group leaves a configured
  temperature range during the configured control period.

TemperatureBot reads the AE-200 `Mode` field from device status, promotes it to
the `/api/v1/status` response, and shows it in the FCU table. Commandable modes
are intentionally narrower than reportable modes.

## Current TemperatureBot Policy

TemperatureBot currently allows users to command these AE-200 operation modes:

- `FAN`
- `COOL`
- `DRY`
- `HEAT`
- `AUTO`

TemperatureBot displays other reported AE-200 modes when present. This includes
`LC_AUTO`, which is displayed as `Auto` while preserving the raw `LC_AUTO`
status value. `LC_AUTO` is not commandable: when an operator selects Auto,
TemperatureBot sends `Mode="AUTO"`. If the AE-200 later reports
`Mode="LC_AUTO"`, TemperatureBot displays it as `Auto` and inserts the raw value
only as a disabled option.

The command path is:

1. The FCU mode dropdown in `app/templates/index.html` renders the selectable
   modes.
2. `app/static/unit_speed.js` restricts browser-submitted modes to
   `FCU_MODE_OPTIONS`.
3. `app/models.py` validates `/api/v1/set_mode` with the `ModeControl`
   Pydantic model.
4. `app/ae200.py` validates the mode against `AE200_ALLOWED_SET_MODES`.
5. `app/ae200.py` sends the selected token as the AE-200 XML attribute
   `Mode="<token>"`. Selecting Auto sends `Mode="AUTO"`; TemperatureBot does
   not translate it to `LC_AUTO`.

## Mode Handling

| AE-200 mode | Meaning in AE-200 terms | TemperatureBot handling |
| --- | --- | --- |
| `COOL` | Cooling operation. Uses the normal cooling set-temperature range for the indoor unit model. | Commandable from the FCU UI and `/api/v1/set_mode`. Sent as `Mode="COOL"`. |
| `DRY` | Dry/dehumidification operation. The AE-200 manuals list this as `Dry`; TemperatureBot uses the uppercase protocol token `DRY`, matching the existing uppercase mode tokens. The manuals also list a normal `Cool/Dry` set-temperature range, so TemperatureBot treats `SetTemp` as active in Dry mode. | Commandable from the FCU UI and `/api/v1/set_mode`. Sent as `Mode="DRY"`. Rule Set Range remains editable for local rules, but AE-200 Auto range behavior is not active in Dry mode. |
| `FAN` | Fan-only operation. This is the AE-200 operation mode, not the same as TemperatureBot's fan-speed control. | Commandable from the FCU UI and `/api/v1/set_mode`. Sent as `Mode="FAN"`. |
| `HEAT` | Heating operation. Uses the normal heating set-temperature range for the indoor unit model. | Commandable from the FCU UI and `/api/v1/set_mode`. Sent as `Mode="HEAT"`. |
| `AUTO` | Automatic heat/cool changeover. The unit/controller chooses heating or cooling. The AE-200 manuals describe Auto dual setpoint in terms of separate Cool and Heat set temperatures; Dry and Fan are listed as separate operation modes, not Auto outcomes. | Commandable from the FCU mode dropdown. Sent as `Mode="AUTO"`, not `Mode="LC_AUTO"`. TemperatureBot displays and writes the Auto Heat/Cool setpoint range. |
| `LC_AUTO` | A reported AE-200 auto-like token seen in TemperatureBot sample data. | Received from the AE-200 as status, displayed as `Auto`, but not commandable. TemperatureBot treats it as reported controller state and does not send it as a mode command. |
| `SETBACK` or other Setback-like value | AE-200 Setback is range-protection behavior. The manuals describe Setback Control as starting heating when a stopped group drops below a minimum temperature, and starting cooling when a stopped group rises above a maximum temperature, during the configured Setback Control period. The controller stops that operation and restores the original set temperature when the control period ends or when the room temperature returns by the documented hysteresis. | Displayed if reported, but not commandable. TemperatureBot does not configure Setback Control time periods, minimum/maximum setback temperatures, dual set points, or the AE-200A/AE-50A vs AE-200E/AE-50E availability distinction. |

## Setback Details

Setback is not just another simple single-setpoint mode.

The AE-200 manual describes Night Setback Control as a protective control that
acts while a group is stopped:

- If room temperature drops below the configured minimum during the control
  period, the AE-200 starts heating automatically.
- If room temperature rises above the configured maximum during the control
  period, the AE-200 starts cooling automatically.
- When the control period ends, or when temperature returns far enough toward
  the allowed range, the AE-200 stops that automatic operation and restores the
  original set temperature.

This behavior depends on AE-200-side configuration that TemperatureBot does not
currently expose: control period, minimum temperature, maximum temperature,
eligible groups, and controller/model support. It also depends on a reliable
room-temperature source; the manual warns that return-air temperature can be
misleading when an indoor unit is stopped and room air is stagnant.

For those reasons, TemperatureBot should not expose Setback as a simple
selectable mode unless it also gains explicit Setback configuration and
read-back support.

## Auto Mode Details

Our AE-200 handles Auto mode. In TemperatureBot, Auto is commandable as an
operation mode. When the reported mode is `AUTO` or `LC_AUTO`, the FCU Set Temp
column exposes an editable Heat/Cool range. TemperatureBot writes that range by
sending one AE-200 set request containing both `SetTemp1="<cool set temp>"` and
`SetTemp2="<heat set temp>"` for the target Mnet group.

The AE-200 manuals list Auto as an air-conditioner operation mode, but also note
that indoor units with dual-set-point support can use separate Cool and Heat set
temperatures when the mode is Auto or Setback. Dry and Fan are listed alongside
Auto as separate operation modes. We therefore treat Auto as heat/cool automatic
changeover only; we do not model Auto as switching to Dry or Fan.

In the AE-200 UI, Auto's range is set by editing the two Auto setpoints:

- The top of the range is the Cool set temperature.
- The bottom of the range is the Heat set temperature.

In AE-200 status payloads, the corresponding values are `SetTemp1` for the Cool
set temperature and `SetTemp2` for the Heat set temperature. The `AutoMin` and
`AutoMax` fields are the allowable Auto-mode limits for the unit, not the
operator-selected top and bottom of the current Auto range. TemperatureBot
promotes these fields to `/api/v1/status` as:

- `cool_set_temp_c`
- `heat_set_temp_c`
- `auto_min_c`
- `auto_max_c`

When the reported operation mode is `AUTO` or `LC_AUTO`, the FCU Set Temp column
shows an editable Heat/Cool range control rather than the single setpoint
increment/decrement control. Both values display as `Auto` in the operation-mode
UI, but only `AUTO` is sent back to the AE-200 when Auto is commanded.

Live verification on July 11, 2026 confirmed that a single AE-200 set request
with both `SetTemp1` and `SetTemp2` updates the Auto Heat/Cool range. The test
used Mnet group `2` (`Area 51`) while `Drive="OFF"`: `SetTemp1`/`SetTemp2`
changed from `24`/`19` to `25`/`20`, and then restored to `24`/`19`, with each
state confirmed by an AE-200 readback.

## Humidity and Dry

The AE-200 ecosystem can display and use humidity data when compatible hardware
is installed and configured. The manuals mention humidity readings from
compatible remote-controller sensors and temperature/humidity sensors connected
through an AI controller. The technical manual also says drying operation can be
controlled using the humidity sensor on the remote controller.

TemperatureBot requests the AE-200 humidity-related fields `RoomHumidity`,
`InletHumidity`, `SetHumidity`, and `Humid`. In the currently checked-in sample
payloads and prior production-copy investigation, those fields have not provided
usable per-FCU humidity: `RoomHumidity` is empty, `InletHumidity` and
`SetHumidity` are `0`, and `Humid` is `OFF`.

TemperatureBot therefore treats `DRY` as an explicit operator-selected mode, not
as an automatic consequence of Auto mode or a humidity automation. The checked-in
AE-200 manual does not indicate that temperature is ignored in Dry mode: it lists
`Cool/Dry` as sharing the `19°C-30°C` set-temperature range, and the External
Temperature Interlock section explicitly describes set-temperature adjustment for
`Cool` and `Dry` modes. TemperatureBot should therefore continue to send and
display the single `SetTemp` control in Dry mode, while leaving Rule Set Range as a
local/rules value unless the mode is Auto.

## Fan Speed Auto Is Separate

TemperatureBot also has fan-speed controls. Fan-speed `AUTO` is not an AE-200
operation mode. It is a fan-speed value (`FanSpeed="AUTO"`) and is already
handled separately from `Mode`.

This distinction matters in the UI:

- Operation mode `FAN` means fan-only HVAC operation.
- Fan-speed `AUTO` means the unit chooses fan speed automatically.
- Operation mode `AUTO` means automatic heating/cooling changeover.

## Guideline for Future Changes

Do not add a mode to the FCU dropdown merely because the AE-200 can report it.
Make a mode commandable only when TemperatureBot can represent the full operator
intent and the relevant AE-200 read-back fields.

For the current app, the safe commandable set is `FAN`, `COOL`, `DRY`, `HEAT`,
and `AUTO`.
