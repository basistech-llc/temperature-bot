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
from collections.abc import Callable
import requests


from .constants import RULES_ENGINE_DEVICE_NAME
from .device_types import DEVICE_TYPE_INTERNAL
from .paths import BIN_DIR
from . import db
from . import db_alerts
from . import presence
from . import ae200
from . import slack

from .models import (
    AutoSetTempControl,
    SpeedControl,
    DriveControl,
    ModeControl,
    SetTempControl,
    Device,
    AlertEventNotification,
    AlertEventRecord,
    AlertEventType,
    AlertRecord,
    AlertRuleDevice,
    AlertRuleEvaluation,
    AlertRuleResult,
    AlertRuleState,
    RuleResult,
)

logger = logging.getLogger(__name__)

RULES_DEVICE_NAME = RULES_ENGINE_DEVICE_NAME
RULES_PATH = Path(BIN_DIR) / "rules.py"

RULES_DISABLED_MESSAGE = "Master rules switch is OFF; skipping HVAC rule execution"
RULES_TIME_SUSPENDED_MESSAGE = "all rules disabled (time-limited suspension)"

ALERT_REPEAT_FIRST_HOUR_SECONDS = 5 * 60
ALERT_REPEAT_FIRST_DAY_SECONDS = 60 * 60
ALERT_REPEAT_LATER_SECONDS = 4 * 60 * 60
ALERT_FIRST_HOUR_SECONDS = 60 * 60
ALERT_FIRST_DAY_SECONDS = 24 * 60 * 60
ALERT_DELIVERY_RETRY_INITIAL_SECONDS = 60
ALERT_DELIVERY_RETRY_MAX_SECONDS = 60 * 60
ALERT_DELIVERY_MAX_ATTEMPTS = 24
ALERT_DELIVERY_OUTBOX_BATCH_SIZE = 100
DEFAULT_ALERT_RULE_HISTORY_SECONDS = 10 * 60
ACTION_RULE_AQI_MAX_AGE_SECONDS = 2 * 60 * 60
AQI_MISSING_MESSAGE = "Cannot run HVAC rules: no outdoor AQI observation is available"
AQI_STALE_MESSAGE = "Cannot run HVAC rules: outdoor AQI observation is stale"
AQI_FUTURE_MESSAGE = "Cannot run HVAC rules: outdoor AQI observation is in the future"

AlertNotifier = Callable[[str], str | None]
AlertRuleFunction = Callable[[AlertRuleDevice, datetime.datetime], object]


def get_room_presence(conn, room_id: int, *, when: int | None = None):
    """Return canonical room presence for rule implementations."""
    return presence.get_presence_for_room(conn, room_id, at_time=when)

def rules_id(conn):
    return db.get_or_create_device_id(
        conn, RULES_DEVICE_NAME, device_type=DEVICE_TYPE_INTERNAL
    )

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
    device_id = db.get_device_id(conn, RULES_DEVICE_NAME)
    if device_id is None:
        return 0
    until = db.device_rules_disabled_until(conn, device_id)
    logger.info("all rules disabled until %s", until)
    return until if until else 0

def disable_all_rules(conn, seconds: int):
    """Enter a database engtry to disable the rules for a period of seconds.
    :param seconds: how long to disable rules for
    """
    logger.info("disable_all_rules(%s)", seconds)
    db.disable_rules_for_device(conn, rules_id(conn), seconds)

def get_rules():
    """Returns the rules as a text"""
    return RULES_PATH.read_text(encoding="utf-8")

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


def set_body_auto_set_temp(conn, body: AutoSetTempControl, ipaddr, agent):
    """Set the Auto-mode Heat and Cool setpoints for a unit."""

    unit_id = db.get_ae200_unit(conn, body.device_id)
    data = ae200.get_device_info(unit_id)
    current_cool = data.get(ae200.AE200_COOL_SET_TEMP_KEY)
    current_heat = data.get(ae200.AE200_HEAT_SET_TEMP_KEY)
    current_value_str = f"Heat={current_heat or ''} Cool={current_cool or ''}"
    new_value_str = f"Heat={body.heat_set_temp_c} Cool={body.cool_set_temp_c}"
    logger.info(
        "set_body_auto_set_temp body=[%s] ipaddr=%s agent=%s. current=%s",
        body,
        ipaddr,
        agent,
        current_value_str,
    )

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
        ae200.set_auto_set_temps(
            unit_id,
            heat_set_temp_c=body.heat_set_temp_c,
            cool_set_temp_c=body.cool_set_temp_c,
        )
        data = ae200.get_device_info(unit_id)

    data[ae200.AE200_HEAT_SET_TEMP_KEY] = str(body.heat_set_temp_c)
    data[ae200.AE200_COOL_SET_TEMP_KEY] = str(body.cool_set_temp_c)
    temp = data.get("InletTemp", None)
    db.insert_devlog_entry(conn, device_id=body.device_id, temp=temp, statusdict=data)
    return {
        "unit": unit_id,
        "temp": temp,
        "device_id": body.device_id,
        "heat_set_temp_c": body.heat_set_temp_c,
        "cool_set_temp_c": body.cool_set_temp_c,
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


def _rule_datetime(when=None):
    if when is None:
        return datetime.datetime.now()
    if isinstance(when, datetime.datetime):
        return when
    return datetime.datetime.fromtimestamp(when)


def _append_rule_result(results, device_id: int, result: RuleResult):
    if result.drive is not None:
        results.append(f"Device {device_id} drive set to {result.drive}")
    if result.fan_speed is not None:
        results.append(f"Device {device_id} speed set to {result.fan_speed}")


def _require_rule_result(result) -> RuleResult:
    if isinstance(result, RuleResult):
        return result
    raise TypeError(
        f"run_rules_for_device returned {type(result).__name__}, expected RuleResult"
    )


def _commit_rule_result(conn, dev: Device, result: RuleResult):
    if result.drive is not None:
        set_body_drive(
            conn,
            DriveControl(device_id=dev.device_id, drive=ae200.DRIVE_NAMES[result.drive]),
            "n/a",
            "rule",
        )
    if result.fan_speed is not None:
        set_body_fan_speed(
            conn,
            SpeedControl(
                device_id=dev.device_id,
                fan_speed=ae200.FAN_SPEED_NAMES[result.fan_speed],
            ),
            "n/a",
            "rule",
        )


def _record_action_rule_failure(conn, devdict, error: Exception, *, commit: bool):
    device_id = devdict["device_id"]
    error_name = type(error).__name__
    message = f"Device {device_id} action-rule failure: {error_name}: {error}"
    logger.exception("Device %s action-rule failure: %s: %s", device_id, error_name, error)
    if commit:
        try:
            db.insert_action_rule_failure(
                conn,
                device_id=device_id,
                ae200_device_id=devdict.get("ae200_device_id"),
                error_type=error_name,
                error_message=str(error),
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception("Could not audit action-rule failure for device %s", device_id)
    return message


def next_alert_notification_at(first_notification_time: int, last_event_time: int) -> int:
    """Return the next reminder boundary for the requested escalating cadence."""
    first_hour_end = first_notification_time + ALERT_FIRST_HOUR_SECONDS
    first_day_end = first_notification_time + ALERT_FIRST_DAY_SECONDS
    if last_event_time < first_hour_end:
        return min(
            last_event_time + ALERT_REPEAT_FIRST_HOUR_SECONDS,
            first_hour_end,
        )
    if last_event_time < first_day_end:
        return min(
            last_event_time + ALERT_REPEAT_FIRST_DAY_SECONDS,
            first_day_end,
        )
    return last_event_time + ALERT_REPEAT_LATER_SECONDS


def _require_alert_rule_results(results) -> list[AlertRuleResult]:
    if results is None:
        return []
    if not isinstance(results, (list, tuple)):
        raise TypeError(
            "run_alert_rules_for_device returned "
            f"{type(results).__name__}, expected a list"
        )
    return [
        result
        if isinstance(result, AlertRuleResult)
        else AlertRuleResult.model_validate(result)
        for result in results
    ]


def _invoke_alert_rule(
    rule_function: AlertRuleFunction,
    device: AlertRuleDevice,
    now: datetime.datetime,
) -> object:
    return rule_function(device, now)


def _deliver_alert_event(
    conn,
    notification: AlertEventNotification,
    notifier: AlertNotifier,
) -> None:
    event = db_alerts.create_alert_event(
        conn,
        alert_id=notification.alert_id,
        event_time=notification.event_time,
        event_type=notification.event_type,
        message=notification.message,
    )
    conn.commit()
    logger.warning("Alert %s: %s", notification.event_type.value, notification.message)
    _attempt_alert_event_delivery(
        conn,
        event,
        attempted_at=notification.event_time,
        notifier=notifier,
    )


def _alert_delivery_retry_seconds(
    attempt_number: int, error: Exception | None = None
) -> int:
    """Return capped exponential backoff, extended by Slack Retry-After."""
    exponent = min(max(0, attempt_number - 1), 16)
    delay: int = min(
        ALERT_DELIVERY_RETRY_INITIAL_SECONDS * (2**exponent),
        ALERT_DELIVERY_RETRY_MAX_SECONDS,
    )
    if isinstance(error, requests.exceptions.HTTPError) and error.response is not None:
        retry_after = error.response.headers.get("Retry-After")
        try:
            if retry_after:
                retry_after_seconds = int(str(retry_after))
                delay = max(delay, retry_after_seconds)
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid Slack Retry-After value %r", retry_after)
    return delay


def _attempt_alert_event_delivery(
    conn,
    event: AlertEventRecord,
    *,
    attempted_at: int,
    notifier: AlertNotifier,
) -> bool:
    """Claim and attempt one outbox event, recording a durable outcome."""
    attempt_number = event.slack_attempt_count + 1
    provisional_retry_at = attempted_at + _alert_delivery_retry_seconds(attempt_number)
    if not db_alerts.claim_alert_event_delivery(
        conn,
        event.alert_event_id,
        attempted_at=attempted_at,
        retry_at=provisional_retry_at,
    ):
        return False
    try:
        message_ts = notifier(event.message)
        if not message_ts:
            raise RuntimeError("Slack did not return a message timestamp")
    except Exception as error:  # pylint: disable=broad-except
        logger.exception("Failed to deliver alert event %s to Slack", event.alert_event_id)
        terminal = attempt_number >= ALERT_DELIVERY_MAX_ATTEMPTS
        retry_at = None
        if not terminal:
            retry_at = attempted_at + _alert_delivery_retry_seconds(
                attempt_number, error
            )
        db_alerts.mark_alert_event_failed(
            conn,
            event.alert_event_id,
            error=str(error),
            retry_at=retry_at,
            terminal=terminal,
        )
        return False
    db_alerts.mark_alert_event_sent(
        conn,
        event.alert_event_id,
        message_ts=message_ts,
    )
    return True


def _deliver_due_alert_events(conn, *, now: int, notifier: AlertNotifier) -> None:
    """Drain one bounded batch of due pending and failed outbox events."""
    for event in db_alerts.get_due_alert_events(
        conn,
        now=now,
        limit=ALERT_DELIVERY_OUTBOX_BATCH_SIZE,
    ):
        _attempt_alert_event_delivery(
            conn,
            event,
            attempted_at=now,
            notifier=notifier,
        )


def _remind_active_alert(
    conn,
    active_alert: AlertRecord,
    evaluation: AlertRuleEvaluation,
    *,
    notifier: AlertNotifier,
) -> str | None:
    result = evaluation.result
    now = evaluation.now
    indeterminate = result.state == AlertRuleState.INDETERMINATE
    qualifier = "indeterminate " if indeterminate else ""
    summary = (
        f"Device {evaluation.device_id} reminded {qualifier}{result.alert_type}"
    )
    event_window = db_alerts.get_alert_event_window(conn, active_alert.alert_id)
    reminder_due = event_window is None or now >= next_alert_notification_at(
        event_window.first_event_time, event_window.last_event_time
    )
    if not reminder_due:
        return None
    if not evaluation.commit:
        return summary.replace(" reminded ", " would remind ")
    _deliver_alert_event(
        conn,
        AlertEventNotification(
            alert_id=active_alert.alert_id,
            event_time=now,
            event_type=AlertEventType.REMINDER,
            message=result.message,
        ),
        notifier=notifier,
    )
    return summary


def _apply_active_alert_result(
    conn,
    active_alert: AlertRecord | None,
    evaluation: AlertRuleEvaluation,
    notifier: AlertNotifier,
) -> str | None:
    device_id = evaluation.device_id
    result = evaluation.result
    if active_alert is None:
        if not evaluation.commit:
            return f"Device {device_id} would trigger {result.alert_type}"
        creation = db_alerts.get_or_create_active_alert_record(
            conn,
            device_id=device_id,
            alert_type=result.alert_type,
            start_time=result.started_at or evaluation.now,
        )
        active_alert = creation.alert
        if not creation.created:
            return _remind_active_alert(conn, active_alert, evaluation, notifier=notifier)
        _deliver_alert_event(
            conn,
            AlertEventNotification(
                alert_id=active_alert.alert_id,
                event_time=evaluation.now,
                event_type=AlertEventType.TRIGGERED,
                message=result.message,
            ),
            notifier=notifier,
        )
        return f"Device {device_id} triggered {result.alert_type}"
    return _remind_active_alert(conn, active_alert, evaluation, notifier=notifier)


def _apply_inactive_alert_result(
    conn,
    active_alert: AlertRecord | None,
    evaluation: AlertRuleEvaluation,
    notifier: AlertNotifier,
) -> str | None:
    if active_alert is None:
        return None
    device_id = evaluation.device_id
    result = evaluation.result
    if not evaluation.commit:
        return f"Device {device_id} would resolve {result.alert_type}"
    db_alerts.resolve_alert_record(conn, active_alert.alert_id, end_time=evaluation.now)
    _deliver_alert_event(
        conn,
        AlertEventNotification(
            alert_id=active_alert.alert_id,
            event_time=evaluation.now,
            event_type=AlertEventType.RESOLVED,
            message=result.resolved_message,
        ),
        notifier=notifier,
    )
    return f"Device {device_id} resolved {result.alert_type}"


def _apply_alert_rule_result(
    conn,
    evaluation: AlertRuleEvaluation,
    notifier: AlertNotifier,
) -> str | None:
    result = evaluation.result
    active_alert = db_alerts.get_active_alert_record(
        conn, evaluation.device_id, result.alert_type
    )
    if result.state == AlertRuleState.ACTIVE:
        return _apply_active_alert_result(conn, active_alert, evaluation, notifier)
    if result.state == AlertRuleState.INACTIVE:
        return _apply_inactive_alert_result(conn, active_alert, evaluation, notifier)
    if active_alert is None:
        return None
    return _remind_active_alert(conn, active_alert, evaluation, notifier=notifier)


def apply_alert_evaluation(
    conn,
    evaluation: AlertRuleEvaluation,
    *,
    notifier: AlertNotifier | None = None,
) -> str | None:
    """Apply one typed alert observation through the shared lifecycle."""
    return _apply_alert_rule_result(conn, evaluation, notifier or slack.post)


def run_alert_rules(
    conn,
    when=None,
    *,
    commit: bool = False,
    notifier: AlertNotifier | None = None,
) -> str:
    """Evaluate monitoring-only rules regardless of the HVAC master switch."""
    now = _rule_datetime(when)
    now_ts = int(now.timestamp())
    deliver = notifier or slack.post
    if commit:
        _deliver_due_alert_events(conn, now=now_ts, notifier=deliver)
    virtual_module = types.ModuleType("ephemeral_alert_rule_namespace")
    virtual_module.__file__ = str(RULES_PATH)
    virtual_module.__dict__["__builtins__"] = __builtins__
    try:
        exec(get_rules(), virtual_module.__dict__)  # pylint: disable=exec-used
    except Exception:  # pylint: disable=broad-except
        logger.exception("Failed to compile alert rules from %s", RULES_PATH)
        return "Cannot compile alert rules"

    rule_function = getattr(virtual_module, "run_alert_rules_for_device", None)
    if not isinstance(rule_function, types.FunctionType):
        logger.warning("No run_alert_rules_for_device function in %s", RULES_PATH)
        return "No alert rules"

    history_seconds = getattr(
        virtual_module,
        "ALERT_RULE_HISTORY_SECONDS",
        DEFAULT_ALERT_RULE_HISTORY_SECONDS,
    )
    if not isinstance(history_seconds, int) or history_seconds <= 0:
        logger.error("ALERT_RULE_HISTORY_SECONDS must be a positive integer")
        return "Invalid alert-rule history"

    results: list[str] = []
    for device in db_alerts.get_alert_rule_devices(
        conn, now=now_ts, history_seconds=history_seconds
    ):
        try:
            alert_results = _require_alert_rule_results(
                _invoke_alert_rule(rule_function, device, now)
            )
            for alert_result in alert_results:
                summary = apply_alert_evaluation(
                    conn,
                    AlertRuleEvaluation(
                        device_id=device.device_id,
                        result=alert_result,
                        now=now_ts,
                        commit=commit,
                    ),
                    notifier=deliver,
                )
                if summary:
                    results.append(summary)
        except Exception:  # pylint: disable=broad-except
            logger.exception("Failed alert-rule evaluation for device %s", device.device_id)
    return "\n".join(results)


def rules_results(conn, when=None, aqi=50):
    """Reports what would happen if the rules were run at `when` with a specific AQI"""
    logger.debug("when=%s", when)

    results = []
    temps = _temperature_context(conn)

    def set_drive_verbose(device_id, value):
        results.append(f"Device {device_id} drive set to {value}")

    def set_fan_speed_verbose(device_id, value):
        results.append(f"Device {device_id} speed set to {value}")

    rule_namespace = {**db.devices_to_device_id(conn), **get_time_dict(when)}
    rule_namespace.update(
        {
            "AQI": aqi,
            "set_drive": set_drive_verbose,
            "set_fan_speed": set_fan_speed_verbose,
            "get_temp": temps["get_temp"],
            "get_fcu_temp": temps["get_fcu_temp"],
        }
    )

    exec(get_rules(), rule_namespace, rule_namespace)  # pylint: disable=exec-used

    run_rules_for_device = rule_namespace.get("run_rules_for_device")
    if run_rules_for_device is not None:
        now = _rule_datetime(when)
        for devdict in db.get_device_status(conn):
            if not devdict.get("rules_enabled", True):
                continue
            dev = Device(
                erv=db.is_erv_device(devdict),
                name=devdict["device_name"],
                device_id=devdict["device_id"],
                device_type=devdict.get("device_type"),
                rules_enabled=devdict.get("rules_enabled", True),
            )
            res = run_rules_for_device(dev, now, aqi)
            if res is None:
                continue
            res = _require_rule_result(res)
            _append_rule_result(results, dev.device_id, res)

    return "\n".join(results)


def _clear_expired_device_rule_suspensions(conn):
    """Clear expired per-device rules timers and write audit entries."""
    now_ts = int(time.time())
    for device_row in db.fetch_all_device_dicts(conn):
        try:
            disabled_timer_expired = 0 < device_row["disabled_until"] < now_ts
        except (TypeError, KeyError):
            disabled_timer_expired = False

        if disabled_timer_expired:
            db.disable_rules_for_device(
                conn,
                device_row["device_id"],
                0,
                agent="rules runner",
                comment="disabled timer expired",
            )


def _fresh_action_rule_aqi(conn, now: datetime.datetime) -> tuple[int | None, str | None]:
    """Return a fresh AQI value or the reason action rules must stop."""
    observation = db.get_last_aqi(conn)
    if observation is None:
        logger.warning(AQI_MISSING_MESSAGE)
        return None, AQI_MISSING_MESSAGE
    age = int(now.timestamp()) - observation.observed_at
    if age < 0:
        logger.warning("%s: observed_at=%s", AQI_FUTURE_MESSAGE, observation.observed_at)
        return None, AQI_FUTURE_MESSAGE
    if age > ACTION_RULE_AQI_MAX_AGE_SECONDS:
        logger.warning("%s: age=%ss", AQI_STALE_MESSAGE, age)
        return None, AQI_STALE_MESSAGE
    return observation.value, None


def run_all_rules(conn, when=None, commit=False):
    """Run the rules and return a text description of what changed.

    Does not execute commands if all rules are disabled or if rules for the
    specific device are disabled.
    """
    logger.debug("when=%s", when)

    # Global master kill switch: if rules are disabled, exit immediately.
    if not db.get_rules_master_enabled(conn):
        logger.info(RULES_DISABLED_MESSAGE)
        return RULES_DISABLED_MESSAGE

    if all_rules_disabled_until(conn) >= time.time():
        logger.info(RULES_TIME_SUSPENDED_MESSAGE)
        return RULES_TIME_SUSPENDED_MESSAGE

    now = _rule_datetime(when)
    aqi, aqi_error = _fresh_action_rule_aqi(conn, now)
    if aqi_error:
        return aqi_error

    # Get controllable devices from status rows so derived flags are available.
    rule_devices = db.get_device_status(conn)

    # Compile the rules_runner
    virtual_module = types.ModuleType("ephemeral_rule_namespace")
    virtual_module.__file__ = str(RULES_PATH)
    virtual_module.__dict__["__builtins__"] = __builtins__

    try:
        # Execute the compiled code exclusively within the virtual module's dictionary
        exec(get_rules(), virtual_module.__dict__)  # pylint: disable=exec-used

        # Extract and invoke the target function
        if not hasattr(virtual_module, "run_rules_for_device"):
            logger.error(
                "Target function 'run_rules_for_device' not found in %s", RULES_PATH
            )
            return "Cannot run rules"
        run_rules_for_device = getattr(virtual_module, "run_rules_for_device")
    except Exception:  # pylint: disable=broad-except
        logger.exception("Failed to compile rules from %s", RULES_PATH)
        return "Cannot compile rules"

    # Now run the rules for every device
    assert aqi is not None
    rules_res = []
    rules_res.append(f"Rules starting at {now}. commit={commit}")

    for devdict in rule_devices:
        device_id = devdict["device_id"]
        if not devdict.get("rules_enabled", True):
            rules_res.append(f"Device {device_id} rules are disabled")
            continue
        disabled_until = devdict.get("disabled_until") or 0
        if now.timestamp() <= disabled_until:
            rules_res.append(
                f"Device {device_id} is disabled until {disabled_until} "
                f"(currently {now.timestamp()})"
            )
            continue
        dev = Device(
            erv=db.is_erv_device(devdict),
            name=devdict["device_name"],
            device_id=devdict["device_id"],
            device_type=devdict.get("device_type"),
            rules_enabled=devdict.get("rules_enabled", True),
        )
        try:
            res = run_rules_for_device(dev, now, aqi)
            if res is not None:
                res = _require_rule_result(res)
                if commit:
                    _commit_rule_result(conn, dev, res)
                _append_rule_result(rules_res, dev.device_id, res)
        except Exception as error:  # pylint: disable=broad-except
            rules_res.append(
                _record_action_rule_failure(conn, devdict, error, commit=commit)
            )

    if commit:
        _clear_expired_device_rule_suspensions(conn)
    return "\n".join(rules_res)


def run_rules(conn, when=None, commit=False):
    """Backward-compatible entrypoint used by the runner."""
    return run_all_rules(conn, when=when, commit=commit)
