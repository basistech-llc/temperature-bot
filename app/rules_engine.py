"""
Run the rules engine.

The RULES_ENGINE is a special device which, if disabled, disables all rules.
Each individual rule can also be disabled.
Rules are executed with exec(get_rules()) in rules_results.
We loop for every device

"""

import datetime
import types
import time
import logging
from pathlib import Path


from .paths import BIN_DIR
from . import db
from . import ae200
from .models import SpeedControl, DriveControl, ModeControl, SetTempControl,Device,RuleResult

logger = logging.getLogger(__name__)

RULES_DEVICE_NAME = "rules_engine"
RULES_PATH = Path(BIN_DIR) / "rules.py"

RULES_DISABLED_MESSAGE = "Master rules switch is OFF; skipping all rules execution"

def rules_id(conn):
    return db.get_or_create_device_id(conn, RULES_DEVICE_NAME)

def get_time_dict(when=None):
    if when is None:
        when = time.time()
    tm = time.localtime(when)
    return {
        "YEAR": tm.tm_year,
        "MONTH": tm.tm_mon,
        "MDAY": tm.tm_mday,
        "HOUR": tm.tm_hour,
        "MIN": tm.tm_min,
        "SEC": tm.tm_sec,
        "WDAY": tm.tm_wday,
        "YDAY": tm.tm_yday,
        "DST": tm.tm_isdst,
        "MONDAY": tm.tm_wday == 0,
        "TUESDAY": tm.tm_wday == 1,
        "WEDNESDAY": tm.tm_wday == 2,
        "THURSDAY": tm.tm_wday == 3,
        "FRIDAY": tm.tm_wday == 4,
        "SATURDAY": tm.tm_wday == 5,
        "SUNDAY": tm.tm_wday == 6,
        "AM": tm.tm_hour < 12,
        "PM": tm.tm_hour >= 12,
    }


def get_air_dict(conn):
    c = conn.cursor()
    c.execute("SELECT * FROM aqi ORDER BY logtime DESC LIMIT 1")
    row = c.fetchall()
    if not row:
        return {
            "AQI": 0,
            "CO": 0,
            "H": 0,
            "NO2": 0,
            "O3": 0,
            "P": 0,
            "PM10": 0,
            "PM25": 0,
            "SO2": 0,
            "T": 0,
            "W": 0,
        }
    return {k.upper(): v for (k, v) in dict(row[0]).items() if k != "logtime"}


def all_rules_disabled_until(conn) -> int:
    until = db.device_rules_disabled_until(conn, rules_id(conn))
    logging.info("all rules disabled until %s", until)
    return until if until else 0

def disable_all_rules(conn, seconds: int):
    """Enter a database engtry to disable the rules for a period of seconds.
    :param seconds: how long to disable rules for
    """
    logging.info("disable_all_rules(%s)", seconds)
    db.disable_rules_for_device(conn, rules_id(conn), seconds)

def get_rules():
    """Returns the rules as a text"""
    return RULES_PATH.read_text()

def prune_rules(conn):
    """If the rule's disabling has expired, enable it."""
    now = int(time.time())
    c = conn.cursor()
    c.execute(
        "update devices set disabled_until=0 where disabled_until>0 and disabled_until<?",
        (now,),
    )
    conn.commit()

def set_body_fan_speed(conn, body: SpeedControl, ipaddr, agent):
    """
    :param conn: SQLIte3 database conneciton
    :param body: Unit to set, and new speed
    :param ipaddr: Who requested the change
    :param agent: What requested the change.
    """

    unit_id = db.get_ae200_unit(conn, body.device_id)

    # Get the current speed of the unit
    current_fan_speed = ae200.get_device_fan_speed(unit_id)
    if current_fan_speed == body.fan_speed:
        logger.info(
            "set_body_fan_speed body=[%s] ipaddr=%s agent=%s. Speed will not change",
            body,
            ipaddr,
            agent,
        )
    else:
        logger.info(
            "set_body_fan_speed body=[%s] ipaddr=%s agent=%s. Speed changed. current_fan_speed=%s",
            body,
            ipaddr,
            agent,
            current_fan_speed,
        )
        db.insert_changelog(
            conn,
            ipaddr=ipaddr,
            device_id=body.device_id,
            ae200_device_id=unit_id,
            current_values=str(current_fan_speed),
            new_value=str(body.fan_speed),
            agent=agent,
        )
        ae200.set_fan_speed(unit_id, body.fan_speed)
    data = ae200.get_device_info(unit_id)
    # The hardware may not yet reflect the FanSpeed we just sent (the read-back
    # can race the command), so record the commanded value rather than a
    # possibly stale reading. The next runner poll reconciles with hardware.
    data["FanSpeed"] = ae200.FAN_SPEEDS[body.fan_speed]
    temp = data.get("InletTemp", None)
    db.insert_devlog_entry(conn, device_id=body.device_id, temp=temp, statusdict=data)
    return {
        "unit": unit_id,
        "temp": temp,
        "device_id": body.device_id,
        "speed": body.fan_speed,
    }


def set_body_drive(conn, body: DriveControl, ipaddr, agent):
    """
    :param conn: SQLIte3 database conneciton
    :param body: Unit to set, and new drive
    :param ipaddr: Who requested the change
    :param agent: What requested the change.
    """
    logger.debug("==== set_body_drive body=%s", body)

    unit_id = db.get_ae200_unit(conn, body.device_id)

    # Get the current speed of the unit
    current_drive = ae200.get_device_drive(unit_id)
    if current_drive == body.drive:
        logger.info(
            "set_body_drive body=[%s] ipaddr=%s agent=%s. Drive will not change",
            body,
            ipaddr,
            agent,
        )
    else:
        logger.info(
            "set_body_drive body=[%s] ipaddr=%s agent=%s. Drive changed. current_drive=%s",
            body,
            ipaddr,
            agent,
            current_drive,
        )
        db.insert_changelog(
            conn,
            ipaddr=ipaddr,
            device_id=body.device_id,
            ae200_device_id=unit_id,
            current_values=str(current_drive),
            new_value=str(body.drive),
            agent=agent,
        )
        ae200.set_drive(unit_id, body.drive)
    data = ae200.get_device_info(unit_id)
    # The hardware may not yet reflect the Drive we just sent (the read-back can
    # race the command), so record the commanded value rather than a possibly
    # stale reading. Otherwise /status can report the old drive and the UI snaps
    # back to the prior state. The next runner poll reconciles with hardware.
    data["Drive"] = ae200.int_to_drive(body.drive)
    temp = data.get("InletTemp", None)
    db.insert_devlog_entry(conn, device_id=body.device_id, temp=temp, statusdict=data)
    return {
        "unit": unit_id,
        "temp": temp,
        "device_id": body.device_id,
        "drive": body.drive,
    }


def set_body_mode(conn, body: ModeControl, ipaddr, agent):
    """
    Set the AE-200 operation mode for a unit.
    """
    unit_id = db.get_ae200_unit(conn, body.device_id)
    current_mode = ae200.get_device_mode(unit_id)
    if current_mode == body.mode:
        logger.info(
            "set_body_mode body=[%s] ipaddr=%s agent=%s. Mode will not change",
            body,
            ipaddr,
            agent,
        )
    else:
        logger.info(
            "set_body_mode body=[%s] ipaddr=%s agent=%s. Mode changed. current_mode=%s",
            body,
            ipaddr,
            agent,
            current_mode,
        )
        db.insert_changelog(
            conn,
            ipaddr=ipaddr,
            device_id=body.device_id,
            ae200_device_id=unit_id,
            current_values=str(current_mode) if current_mode is not None else "",
            new_value=body.mode,
            agent=agent,
        )
        ae200.set_mode(unit_id, body.mode)
    data = ae200.get_device_info(unit_id)
    # The AE-200 read-back can lag a command; keep /status aligned with the
    # operator's selected mode until the next runner poll reconciles hardware.
    data[ae200.AE200_MODE_KEY] = body.mode
    temp = data.get("InletTemp", None)
    db.insert_devlog_entry(conn, device_id=body.device_id, temp=temp, statusdict=data)
    return {
        "unit": unit_id,
        "temp": temp,
        "device_id": body.device_id,
        "mode": body.mode,
    }


def set_body_set_temp(conn, body: SetTempControl, ipaddr, agent):
    """
    Set the target temperature for a unit (in Celsius).
    """

    unit_id = db.get_ae200_unit(conn, body.device_id)

    data = ae200.get_device_info(unit_id)
    current_set_temp = data.get("SetTemp")
    logger.info(
        "set_body_set_temp body=[%s] ipaddr=%s agent=%s. current_set_temp=%s",
        body,
        ipaddr,
        agent,
        current_set_temp,
    )

    # Record change in changelog if the value is actually changing
    try:
        current_value_str = (
            str(current_set_temp) if current_set_temp is not None else ""
        )
        new_value_str = str(body.set_temp_c)
        if current_value_str != new_value_str:
            db.insert_changelog(
                conn,
                ipaddr=ipaddr,
                device_id=body.device_id,
                ae200_device_id=unit_id,
                current_values=current_value_str,
                new_value=new_value_str,
                agent=agent,
            )
            ae200.set_set_temp(unit_id, body.set_temp_c)
            data = ae200.get_device_info(unit_id)
    except (OSError, ValueError, RuntimeError) as exc:  # pragma: no cover - defensive
        logger.exception("Error while setting set temperature: %s", exc)

    temp = data.get("InletTemp", None)
    db.insert_devlog_entry(conn, device_id=body.device_id, temp=temp, statusdict=data)
    return {
        "unit": unit_id,
        "temp": temp,
        "device_id": body.device_id,
        "set_temp_c": body.set_temp_c,
    }


def _temperature_context(conn):
    """Returns the temperature for all devices"""
    status = db.get_device_status(conn)
    effective_by_id = {}
    raw_by_id = {}
    for device in status:
        raw = device.get("temp10x")
        calculated = device.get("calculated_temp10x")
        if raw is not None:
            raw_by_id[device["device_id"]] = raw / 10
        if calculated is not None:
            effective_by_id[device["device_id"]] = calculated / 10
        elif raw is not None:
            effective_by_id[device["device_id"]] = raw / 10

    def get_temp(device_id):
        return effective_by_id.get(device_id)

    def get_fcu_temp(device_id):
        return raw_by_id.get(device_id)

    return {"get_temp": get_temp, "get_fcu_temp": get_fcu_temp}


###
def rules_results(conn, when=None, aqi=50):
    """Reports what would happen if the rules were run at `when` with a specific AQI"""
    logger.debug("when=%s", when)

    results = []
    temps = _temperature_context(conn)

    def set_drive_verbose(device_id, value):
        results.append(f"Device {device_id} drive set to {value}")

    def set_fan_speed_verbose(device_id, value):
        results.append(f"Device {device_id} speed set to {value}")

    global_vars = {**db.devices_to_device_id(conn), **get_time_dict(when)}
    global_vars["AQI"] = aqi
    local_vars = {
        "set_drive": set_drive_verbose,
        "set_fan_speed": set_fan_speed_verbose,
        "get_temp": temps["get_temp"],
        "get_fcu_temp": temps["get_fcu_temp"],
    }

    exec(get_rules(), global_vars, local_vars)  # pylint: disable=exec-used
    return "\n".join(results)
###

def run_all_rules(conn, when=None, commit=False, ):
    """Run the rules now and returns a text descirption of what changed.
    Does not execute command if all rules are disabled or if the rules for the sepcific device are disabled
    """
    logger.debug("when=%s", when)

    # Global master kill switch: if rules are disabled, exit immediately.
    if not db.get_rules_master_enabled(conn):
        logger.info(RULES_DISABLED_MESSAGE)
        return RULES_DISABLED_MESSAGE

    # Get all of the devices, and determine which are disabled
    all_devices = db.fetch_all_device_dicts(conn)

    # Compile the rules_runner
    virtual_module = types.ModuleType("ephemeral_rule_namespace")
    virtual_module.__file__ = str(RULES_PATH)
    virtual_module.__builtins__ = __builtins__

    try:
        # Execute the compiled code exclusively within the virtual module's dictionary
        exec(get_rules(), virtual_module.__dict__) # pylint: disable=exec-used

        # Extract and invoke the target function
        if not hasattr(virtual_module, 'run_rules_for_device'):
            logger.error("Target function 'run_rules' not found in %s", RULES_PATH)
            return "Cannot run rules"
        run_rules_for_device = getattr(virtual_module, 'run_rules_for_device')
    except Exception as e:      # pylint: disable=broad-except
        logger.error("Execution of run_rules failed: %s", e)
        return "Cannot compile rules"

    # Now run the rules for every device
    now = datetime.datetime.now()
    aqi = db.get_last_aqi(conn)
    rules_res = []
    rules_res.append(f"Rules starting at {now}. commit={commit}")

    for devdict in all_devices:
        device_id = devdict['device_id']
        disabled_until = devdict.get("disabled_until",0)
        if now.timestamp() <= disabled_until:
            rules_res.append(f"Device {device_id} is disabled until {disabled_until} (currently {now.timestamp()})")
            continue
        dev = Device(erv=db.is_erv_device(devdict), name=devdict['device_name'], device_id=devdict['device_id'])
        res = run_rules_for_device(dev, now, aqi)
        if res is not None:
            assert isinstance(res,RuleResult)
            if commit:
                set_body_drive(conn, DriveControl(device_id=dev.device_id, drive=res.drive), "n/a", "rule")
                set_body_fan_speed(conn, SpeedControl(device_id=dev.device_id, fan_speed=res.fan_speed), "n/a", "rule")
            rules_res.append(str(res))

    # finally, if the time has passed for any rule, set to 0
    now = int(time.time())
    for dev in all_devices:
        try:
            disabled_timer_expired = 0 < dev["disabled_until"] < now
        except (TypeError, KeyError):
            disabled_timer_expired = False

        # Only clear the timer (and log) when a non-zero disabled_until has
        # actually expired. This avoids spamming the changelog every time the
        # rules runner executes for devices that are not currently disabled.
        if disabled_timer_expired:
            db.disable_rules_for_device(
                conn,
                dev["device_id"],
                0,
                agent="rules runner",
                comment="disabled timer expired",
            )
    return "\n".join(rules_res)
