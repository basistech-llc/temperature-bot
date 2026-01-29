"""
Alert-related database operations.
Uses the same schema and connection conventions as app.db.
"""

import json
import logging
import time

logger = logging.getLogger(__name__)


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
            status_json, status_logtime = get_alert_device_status(
                conn, device_id_val, start_time
            )
            if status_json:
                details = extract_relevant_status_fields(status_json)
                if details:
                    details["status_timestamp"] = status_logtime
                    alert_dict["details"] = details

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
            status_json, status_logtime = get_alert_device_status(
                conn, device_id_val, start_time
            )
            if status_json:
                details = extract_relevant_status_fields(status_json)
                if details:
                    details["status_timestamp"] = status_logtime
                    alert_dict["details"] = details

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
