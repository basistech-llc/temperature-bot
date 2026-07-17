"""
Alert-related database operations.
Uses the same schema and connection conventions as app.db.
"""

import json
import logging
import time

from . import ae200
from .models import (
    AlertDeliveryStatus,
    AlertEventRecord,
    AlertEventType,
    AlertRecord,
    AlertRuleDevice,
    StatusPayload,
)

logger = logging.getLogger(__name__)


def _canonical_status_json(status_json: str) -> str:
    """Normalize a vendor payload so key order does not look like a value change."""
    return json.dumps(json.loads(status_json), sort_keys=True, separators=(",", ":"))


def get_alert_rule_devices(conn, *, now: int) -> list[AlertRuleDevice]:
    """Return air-monitor observations with their contiguous exact-value run.

    ``devlog`` splits identical payloads at ``MAX_DURATION``. Walking backward
    across adjacent, equivalent rows preserves the real unchanged start time.
    """
    devices = conn.execute(
        """
        SELECT device_id, device_name, device_type
        FROM devices
        WHERE aqi_mon=1
        ORDER BY device_name
        """
    ).fetchall()
    contexts: list[AlertRuleDevice] = []
    for device in devices:
        rows = conn.execute(
            """
            SELECT logtime, duration, status_json
            FROM devlog
            WHERE device_id=? AND logtime<=? AND status_json IS NOT NULL
            ORDER BY logtime DESC, log_id DESC
            """,
            (device["device_id"], now),
        )
        latest = rows.fetchone()
        if latest is None:
            continue
        try:
            latest_status = StatusPayload.model_validate_json(latest["status_json"])
            latest_canonical = _canonical_status_json(latest["status_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning(
                "Ignoring invalid status payload for alert device %s",
                device["device_id"],
            )
            continue

        latest_duration = max(1, int(latest["duration"] or 1))
        observed_through = min(now, int(latest["logtime"]) + latest_duration - 1)
        unchanged_since = int(latest["logtime"])

        for row in rows:
            try:
                same_status = (
                    _canonical_status_json(row["status_json"]) == latest_canonical
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                break
            row_duration = max(1, int(row["duration"] or 1))
            row_end = min(now, int(row["logtime"]) + row_duration - 1)
            if not same_status or row_end < unchanged_since - 1:
                break
            unchanged_since = int(row["logtime"])

        contexts.append(
            AlertRuleDevice(
                device_id=device["device_id"],
                name=device["device_name"],
                device_type=device["device_type"],
                status=latest_status,
                unchanged_since=unchanged_since,
                observed_through=observed_through,
                unchanged_for_seconds=max(0, observed_through - unchanged_since),
                reading_age_seconds=max(0, now - observed_through),
            )
        )
    return contexts


def get_active_alert_record(
    conn, device_id: int, alert_type: str
) -> AlertRecord | None:
    """Return the active alert for a device and rule type, if any."""
    row = conn.execute(
        """
        SELECT alert_id, device_id, alert_type, alert_value, start_time, end_time
        FROM alerts
        WHERE device_id=? AND alert_type=? AND end_time IS NULL
        ORDER BY alert_id DESC
        LIMIT 1
        """,
        (device_id, alert_type),
    ).fetchone()
    return AlertRecord.model_validate(dict(row)) if row else None


def create_alert_record(
    conn, *, device_id: int, alert_type: str, start_time: int
) -> AlertRecord:
    """Create active alert state without committing the caller's transaction."""
    cursor = conn.execute(
        """
        INSERT INTO alerts (device_id, alert_type, alert_value, start_time, end_time)
        VALUES (?, ?, 'ON', ?, NULL)
        """,
        (device_id, alert_type, start_time),
    )
    return AlertRecord(
        alert_id=int(cursor.lastrowid),
        device_id=device_id,
        alert_type=alert_type,
        alert_value="ON",
        start_time=start_time,
    )


def resolve_alert_record(conn, alert_id: int, *, end_time: int) -> None:
    """Close an active alert without committing the caller's transaction."""
    conn.execute(
        "UPDATE alerts SET end_time=? WHERE alert_id=? AND end_time IS NULL",
        (end_time, alert_id),
    )


def get_latest_alert_event(conn, alert_id: int) -> AlertEventRecord | None:
    """Return the newest logged notification for an alert."""
    row = conn.execute(
        """
        SELECT alert_event_id, alert_id, event_time, event_type, message,
               slack_status, slack_message_ts, slack_error,
               slack_attempt_count, slack_last_attempt_time,
               slack_next_attempt_time, slack_terminal
        FROM alert_events
        WHERE alert_id=?
        ORDER BY event_time DESC, alert_event_id DESC
        LIMIT 1
        """,
        (alert_id,),
    ).fetchone()
    return AlertEventRecord.model_validate(dict(row)) if row else None


def get_due_alert_events(
    conn, *, now: int, limit: int
) -> list[AlertEventRecord]:
    """Return retryable outbox events whose next attempt is due."""
    rows = conn.execute(
        """
        SELECT alert_event_id, alert_id, event_time, event_type, message,
               slack_status, slack_message_ts, slack_error,
               slack_attempt_count, slack_last_attempt_time,
               slack_next_attempt_time, slack_terminal
        FROM alert_events
        WHERE slack_status IN ('pending', 'failed')
          AND slack_terminal=0
          AND slack_next_attempt_time<=?
        ORDER BY slack_next_attempt_time, alert_event_id
        LIMIT ?
        """,
        (now, limit),
    ).fetchall()
    return [AlertEventRecord.model_validate(dict(row)) for row in rows]


def create_alert_event(
    conn,
    *,
    alert_id: int,
    event_time: int,
    event_type: AlertEventType,
    message: str,
) -> AlertEventRecord:
    """Log an alert event as pending without committing the transaction."""
    cursor = conn.execute(
        """
        INSERT INTO alert_events
            (alert_id, event_time, event_type, message, slack_status,
             slack_next_attempt_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            alert_id,
            event_time,
            event_type.value,
            message,
            AlertDeliveryStatus.PENDING.value,
            event_time,
        ),
    )
    return AlertEventRecord(
        alert_event_id=int(cursor.lastrowid),
        alert_id=alert_id,
        event_time=event_time,
        event_type=event_type,
        message=message,
        slack_status=AlertDeliveryStatus.PENDING,
        slack_next_attempt_time=event_time,
    )


def claim_alert_event_delivery(
    conn,
    alert_event_id: int,
    *,
    attempted_at: int,
    retry_at: int,
) -> bool:
    """Atomically claim a due event and persist its attempt before I/O."""
    cursor = conn.execute(
        """
        UPDATE alert_events
        SET slack_attempt_count=slack_attempt_count+1,
            slack_last_attempt_time=?, slack_next_attempt_time=?,
            slack_error=NULL
        WHERE alert_event_id=?
          AND slack_status IN ('pending', 'failed')
          AND slack_terminal=0
          AND slack_next_attempt_time<=?
        """,
        (attempted_at, retry_at, alert_event_id, attempted_at),
    )
    conn.commit()
    return int(cursor.rowcount) == 1


def mark_alert_event_sent(
    conn,
    alert_event_id: int,
    *,
    message_ts: str,
) -> None:
    """Record successful Slack delivery as terminal."""
    conn.execute(
        """
        UPDATE alert_events
        SET slack_status=?, slack_message_ts=?, slack_error=NULL,
            slack_next_attempt_time=NULL, slack_terminal=1
        WHERE alert_event_id=?
        """,
        (AlertDeliveryStatus.SENT.value, message_ts, alert_event_id),
    )
    conn.commit()


def mark_alert_event_failed(
    conn,
    alert_event_id: int,
    *,
    error: str,
    retry_at: int | None,
    terminal: bool,
) -> None:
    """Record a failed attempt and its next retry or terminal state."""
    conn.execute(
        """
        UPDATE alert_events
        SET slack_status=?, slack_error=?, slack_next_attempt_time=?,
            slack_terminal=?
        WHERE alert_event_id=?
        """,
        (
            AlertDeliveryStatus.FAILED.value,
            error,
            retry_at,
            int(terminal),
            alert_event_id,
        ),
    )
    conn.commit()


def _attach_device_details(conn, alert_dict, device_id, device_name, start_time):
    """Attach device-status details to an alert dict, in place.

    Looks up the device status recorded at the alert's start time and, when
    present, stores the diagnostic fields under ``details`` along with a
    user-facing ``fan_speed_display`` (the raw ``fan_speed`` is the AE200
    protocol code, which is meaningless to users).
    """
    status_json, status_logtime = get_alert_device_status(
        conn, device_id, start_time
    )
    if not status_json:
        return
    details = extract_relevant_status_fields(status_json)
    if not details:
        return
    details["status_timestamp"] = status_logtime
    details["fan_speed_display"] = ae200.friendly_fan_speed_label(
        device_name, details.get("fan_speed")
    )
    alert_dict["details"] = details


def format_alert_type_display(alert_type):
    """
    Convert internal alert type names to user-friendly display names.

    :param alert_type: Internal name ('ErrorSign', 'FilterSign', 'CheckWater')
    :return: User-friendly display name
    """
    mapping = {
        "ErrorSign": "Error",
        "FilterSign": "Filter warning",
        "CheckWater": "Water issue",
        "SensorStuck": "Sensor stuck",
    }
    return mapping.get(alert_type, alert_type)


def extract_relevant_status_fields(status_json):
    """
    Extract relevant diagnostic fields from status_json for alert details.

    :param status_json: JSON string containing device status
    :return: Dictionary with relevant diagnostic fields or None
    """
    if not status_json:
        return None

    try:
        data = json.loads(status_json)
    except (TypeError, json.JSONDecodeError):
        return None

    # Extract key diagnostic fields
    return {
        "mode": data.get("Mode"),
        "drive": data.get("Drive"),
        "inlet_temp": data.get("InletTemp"),
        "set_temp": data.get("SetTemp"),
        "fan_speed": data.get("FanSpeed"),
        "filter_sign": data.get("FilterSign"),
        "check_water": data.get("CheckWater"),
        "error_sign": data.get("ErrorSign"),
        "remote_control": data.get("RemoCon"),
        "group_id": data.get("Group"),
        "hold": data.get("Hold"),
        "ventilation": data.get("Ventilation"),
        "mode_status": data.get("ModeStatus"),
    }


def get_alert_device_status(conn, device_id, alert_start_time):
    """
    Get the device status_json from devlog for the alert start time.
    Handles RLE encoding by looking for records that span the alert time.
    Falls back to nearest entry with status_json if exact span doesn't have status.

    :param conn: database connection
    :param device_id: device ID
    :param alert_start_time: Unix timestamp when alert started
    :return: tuple of (status_json string, logtime int) or (None, None) if not found
    """
    c = conn.cursor()

    # First try: Handle RLE encoding - look for records where alert_start_time falls within the logtime + duration range
    # This works because devlog uses run-length encoding where records extend over time periods
    c.execute(
        """
        SELECT status_json, logtime, duration
        FROM devlog
        WHERE device_id = ?
        AND logtime <= ?
        AND (logtime + duration) >= ?
        AND status_json IS NOT NULL
        ORDER BY logtime DESC
        LIMIT 1
    """,
        (device_id, alert_start_time, alert_start_time),
    )

    row = c.fetchone()
    if row:
        return (row[0], row[1])

    # Fallback: If no spanning entry has status_json, look for the most recent
    # entry with status_json before the alert time. This handles cases where
    # status_json was removed by compression.
    c.execute(
        """
        SELECT status_json, logtime, duration
        FROM devlog
        WHERE device_id = ?
        AND status_json IS NOT NULL
        AND logtime <= ?
        ORDER BY logtime DESC
        LIMIT 1
    """,
        (device_id, alert_start_time),
    )

    row = c.fetchone()
    if row:
        return (row[0], row[1])
    return (None, None)


def insert_or_update_alert(conn, device_id, alert_type, alert_value, logtime=None):
    """
    Insert or update alert state transitions.

    :param conn: database connection
    :param device_id: device ID
    :param alert_type: 'ErrorSign', 'FilterSign', 'CheckWater'
    :param alert_value: 'ON' or 'OFF'
    :param logtime: Unix timestamp (defaults to current time)
    """
    if logtime is None:
        logtime = int(time.time())

    c = conn.cursor()

    # Check if there's an active alert (end_time=NULL) for this device+type
    c.execute(
        """
        SELECT alert_id, alert_value FROM alerts
        WHERE device_id=? AND alert_type=? AND end_time IS NULL
    """,
        (device_id, alert_type),
    )
    active_alert = c.fetchone()

    if active_alert:
        active_id, current_value = active_alert
        if current_value == alert_value:
            # No change, do nothing
            return
        else:
            # Close the active alert
            c.execute(
                "UPDATE alerts SET end_time=? WHERE alert_id=?", (logtime, active_id)
            )

    # If value is 'ON', create new alert
    if alert_value == "ON":
        c.execute(
            """
            INSERT INTO alerts (device_id, alert_type, alert_value, start_time, end_time)
            VALUES (?, ?, ?, ?, NULL)
        """,
            (device_id, alert_type, alert_value, logtime),
        )

    conn.commit()


def get_active_alerts(conn, device_id=None, include_details=False):
    """
    Get all active alerts (end_time IS NULL).

    :param conn: database connection
    :param device_id: optional filter by device
    :param include_details: if True, include device status details
    :return: list of dicts with alert data
    """
    c = conn.cursor()

    query = """
        SELECT a.alert_id, a.device_id, d.device_name, a.alert_type, a.alert_value, a.start_time
        FROM alerts a
        JOIN devices d ON a.device_id = d.device_id
        WHERE a.end_time IS NULL
    """
    args = []

    if device_id:
        query += " AND a.device_id = ?"
        args.append(device_id)

    query += " ORDER BY a.start_time DESC"

    c.execute(query, args)

    alerts = []
    for row in c.fetchall():
        alert_id, device_id_val, device_name, alert_type, alert_value, start_time = row
        age_seconds = int(time.time()) - start_time

        alert_dict = {
            "alert_id": alert_id,
            "device_name": device_name,
            "alert_type": format_alert_type_display(alert_type),
            "alert_value": alert_value,
            "start_time": start_time,
            "age": age_seconds,
        }

        # Add device status details if requested
        if include_details:
            _attach_device_details(
                conn, alert_dict, device_id_val, device_name, start_time
            )

        alerts.append(alert_dict)

    return alerts


def get_alert_history(conn, device_id=None, limit=100, include_details=False):
    """
    Get alert history (all alerts including resolved).

    :param conn: database connection
    :param device_id: optional filter by device
    :param limit: maximum number of alerts to return
    :param include_details: if True, include device status details
    :return: list of dicts with alert data
    """
    c = conn.cursor()

    query = """
        SELECT a.alert_id, a.device_id, d.device_name, a.alert_type, a.alert_value,
               a.start_time, a.end_time
        FROM alerts a
        JOIN devices d ON a.device_id = d.device_id
    """
    args = []

    if device_id:
        query += " WHERE a.device_id = ?"
        args.append(device_id)

    query += " ORDER BY a.start_time DESC LIMIT ?"
    args.append(limit)

    c.execute(query, args)

    alerts = []
    for row in c.fetchall():
        (
            alert_id,
            device_id_val,
            device_name,
            alert_type,
            alert_value,
            start_time,
            end_time,
        ) = row
        duration = None
        if end_time:
            duration = end_time - start_time

        alert_dict = {
            "alert_id": alert_id,
            "device_name": device_name,
            "alert_type": format_alert_type_display(alert_type),
            "alert_value": alert_value,
            "start_time": start_time,
            "end_time": end_time,
            "duration": duration,
        }

        # Add device status details if requested
        if include_details:
            _attach_device_details(
                conn, alert_dict, device_id_val, device_name, start_time
            )

        alerts.append(alert_dict)

    return alerts


def get_alerts_for_device(conn, device_id):
    """
    Get all alerts (active and historical) for a specific device.

    :param conn: database connection
    :param device_id: device ID
    :return: list of dicts with alert data
    """
    c = conn.cursor()

    c.execute(
        """
        SELECT a.alert_id, a.alert_type, a.alert_value, a.start_time, a.end_time
        FROM alerts a
        WHERE a.device_id = ?
        ORDER BY a.start_time DESC
    """,
        (device_id,),
    )

    alerts = []
    for row in c.fetchall():
        alert_id, alert_type, alert_value, start_time, end_time = row
        duration = None
        if end_time:
            duration = end_time - start_time

        alerts.append(
            {
                "alert_id": alert_id,
                "alert_type": format_alert_type_display(alert_type),
                "alert_value": alert_value,
                "start_time": start_time,
                "end_time": end_time,
                "duration": duration,
            }
        )

    return alerts
