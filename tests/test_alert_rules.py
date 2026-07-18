"""Stateful monitoring-rule tests using the real SQLite schema and rules file."""

import json

import requests

from app import db, db_alerts, rules_engine
from app.device_types import DEVICE_SUBTYPE_AIRTHINGS
from app.models import AlertEventType


AIRTHINGS_STATUS = {
    "co2": {"unit": "ppm", "value": 498.0},
    "humidity": {"unit": "pct", "value": 50.0},
    "pm1": {"unit": "mgpc", "value": 9.0},
    "pm25": {"unit": "mgpc", "value": 10.0},
    "pressure": {"unit": "mbar", "value": 1013.3},
    "radonShortTermAvg": {"unit": "bq", "value": 97.0},
    "temp": {"unit": "c", "value": 25.0},
    "voc": {"unit": "ppb", "value": 70.0},
}


def _add_airthings_device(
    conn, name: str = "Airthings Dungeon", *, aqi_mon: int = 1
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO devices (device_name, device_type, device_subtype, aqi_mon)
        VALUES (?, 'SENSOR', ?, ?)
        """,
        (name, DEVICE_SUBTYPE_AIRTHINGS, aqi_mon),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _add_status(conn, device_id: int, logtime: int, duration: int, status) -> None:
    conn.execute(
        """
        INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (device_id, logtime, duration, 250, json.dumps(status)),
    )
    conn.commit()


def test_exact_value_run_ignores_key_order_and_integer_float_notation(
    test_database_conn,
):
    conn = test_database_conn
    device_id = _add_airthings_device(conn)
    prior = {**AIRTHINGS_STATUS, "co2": {"unit": "ppm", "value": 497.0}}
    historical = {
        sensor: {
            **reading,
            "value": (
                int(reading["value"])
                if reading["value"].is_integer()
                else reading["value"]
            ),
        }
        for sensor, reading in AIRTHINGS_STATUS.items()
    }
    _add_status(conn, device_id, 900, 100, prior)
    _add_status(conn, device_id, 1000, 1200, historical)
    _add_status(
        conn,
        device_id,
        2200,
        601,
        dict(reversed(list(AIRTHINGS_STATUS.items()))),
    )

    devices = db_alerts.get_alert_rule_devices(conn, now=2800)

    assert len(devices) == 1
    assert devices[0].unchanged_since == 1000
    assert devices[0].observed_through == 2800
    assert devices[0].unchanged_for_seconds == 1800
    assert devices[0].reading_age_seconds == 0


def test_discovered_airthings_is_monitored_without_dashboard_flag(
    test_database_conn,
):
    conn = test_database_conn
    device_id = _add_airthings_device(conn, name="Dungeon", aqi_mon=0)
    _add_status(conn, device_id, 1000, 601, AIRTHINGS_STATUS)
    delivered: list[str] = []

    result = rules_engine.run_alert_rules(
        conn,
        when=1600,
        commit=True,
        notifier=lambda message: delivered.append(message) or "message-ts",
    )

    assert result == f"Device {device_id} triggered SensorStuck"
    assert len(delivered) == 1
    assert db_alerts.get_active_alert_record(conn, device_id, "SensorStuck") is not None


def test_stuck_alert_lifecycle_and_cadence_ignore_hvac_master_switch(
    test_database_conn,
):
    conn = test_database_conn
    device_id = _add_airthings_device(conn)
    _add_status(conn, device_id, 1000, 601, AIRTHINGS_STATUS)
    db.set_rules_master_enabled(conn, False)
    delivered: list[str] = []

    def notifier(message: str) -> str:
        delivered.append(message)
        return f"message-{len(delivered)}"

    result = rules_engine.run_alert_rules(
        conn, when=1600, commit=True, notifier=notifier
    )
    assert result == f"Device {device_id} triggered SensorStuck"
    assert len(delivered) == 1
    assert "exactly unchanged for 10 minutes" in delivered[0]

    alert = db_alerts.get_active_alert_record(conn, device_id, "SensorStuck")
    assert alert is not None
    assert alert.start_time == 1000
    events = conn.execute(
        "SELECT event_type, slack_status FROM alert_events WHERE alert_id=?",
        (alert.alert_id,),
    ).fetchall()
    assert [tuple(event) for event in events] == [("triggered", "sent")]

    conn.execute(
        "UPDATE devlog SET duration=900 WHERE device_id=? AND logtime=1000",
        (device_id,),
    )
    conn.commit()
    assert not rules_engine.run_alert_rules(
        conn, when=1899, commit=True, notifier=notifier
    )
    assert len(delivered) == 1

    conn.execute(
        "UPDATE devlog SET duration=901 WHERE device_id=? AND logtime=1000",
        (device_id,),
    )
    conn.commit()
    result = rules_engine.run_alert_rules(
        conn, when=1900, commit=True, notifier=notifier
    )
    assert result == f"Device {device_id} reminded SensorStuck"
    assert len(delivered) == 2

    changed = {**AIRTHINGS_STATUS, "co2": {"unit": "ppm", "value": 499.0}}
    _add_status(conn, device_id, 1901, 1, changed)
    result = rules_engine.run_alert_rules(
        conn, when=1901, commit=True, notifier=notifier
    )
    assert result == f"Device {device_id} resolved SensorStuck"
    assert len(delivered) == 3
    assert "is unstuck" in delivered[-1]
    assert db_alerts.get_active_alert_record(conn, device_id, "SensorStuck") is None
    events = conn.execute(
        "SELECT event_type, slack_status FROM alert_events WHERE alert_id=? "
        "ORDER BY alert_event_id",
        (alert.alert_id,),
    ).fetchall()
    assert [tuple(event) for event in events] == [
        ("triggered", "sent"),
        ("reminder", "sent"),
        ("resolved", "sent"),
    ]


def test_stale_input_keeps_active_alert_and_sends_indeterminate_reminder(
    test_database_conn,
):
    conn = test_database_conn
    device_id = _add_airthings_device(conn)
    _add_status(conn, device_id, 1000, 601, AIRTHINGS_STATUS)
    delivered: list[str] = []

    rules_engine.run_alert_rules(
        conn,
        when=1600,
        commit=True,
        notifier=lambda message: delivered.append(message) or "triggered-ts",
    )
    result = rules_engine.run_alert_rules(
        conn,
        when=1900,
        commit=True,
        notifier=lambda message: delivered.append(message) or "reminder-ts",
    )

    assert result == f"Device {device_id} reminded indeterminate SensorStuck"
    assert len(delivered) == 2
    assert "cannot be evaluated" in delivered[-1]
    assert "latest reading is 5 minutes old" in delivered[-1]
    alert = db_alerts.get_active_alert_record(conn, device_id, "SensorStuck")
    assert alert is not None

    changed = {**AIRTHINGS_STATUS, "co2": {"unit": "ppm", "value": 499.0}}
    _add_status(conn, device_id, 1901, 1, changed)
    result = rules_engine.run_alert_rules(
        conn,
        when=1901,
        commit=True,
        notifier=lambda message: delivered.append(message) or "resolved-ts",
    )
    assert result == f"Device {device_id} resolved SensorStuck"
    assert "is unstuck" in delivered[-1]
    assert db_alerts.get_active_alert_record(conn, device_id, "SensorStuck") is None


def test_missing_input_does_not_orphan_existing_active_alert(test_database_conn):
    conn = test_database_conn
    device_id = _add_airthings_device(conn)
    _add_status(conn, device_id, 1000, 601, AIRTHINGS_STATUS)
    rules_engine.run_alert_rules(
        conn, when=1600, commit=True, notifier=lambda _message: "triggered-ts"
    )
    conn.execute("DELETE FROM devlog WHERE device_id=?", (device_id,))
    conn.commit()
    delivered: list[str] = []

    result = rules_engine.run_alert_rules(
        conn,
        when=1900,
        commit=True,
        notifier=lambda message: delivered.append(message) or "reminder-ts",
    )

    assert result == f"Device {device_id} reminded indeterminate SensorStuck"
    assert len(delivered) == 1
    assert "no status reading is available" in delivered[0]
    assert db_alerts.get_active_alert_record(conn, device_id, "SensorStuck") is not None


def test_indeterminate_input_does_not_open_new_alert(test_database_conn):
    conn = test_database_conn
    device_id = _add_airthings_device(conn)
    delivered: list[str] = []

    result = rules_engine.run_alert_rules(
        conn,
        when=1900,
        commit=True,
        notifier=lambda message: delivered.append(message) or "unexpected",
    )

    assert result == ""
    assert not delivered
    assert db_alerts.get_active_alert_record(conn, device_id, "SensorStuck") is None


def test_alert_notification_cadence_boundaries():
    start = 1_000

    assert rules_engine.next_alert_notification_at(start, start + 10 * 60) == (
        start + 15 * 60
    )
    assert rules_engine.next_alert_notification_at(start, start + 55 * 60) == (
        start + 60 * 60
    )
    assert rules_engine.next_alert_notification_at(start, start + 60 * 60) == (
        start + 2 * 60 * 60
    )
    assert rules_engine.next_alert_notification_at(start, start + 23 * 60 * 60) == (
        start + 24 * 60 * 60
    )
    assert rules_engine.next_alert_notification_at(start, start + 24 * 60 * 60) == (
        start + 28 * 60 * 60
    )


def test_alert_is_logged_when_slack_delivery_fails(test_database_conn):
    conn = test_database_conn
    device_id = _add_airthings_device(conn, "Airthings Area 51")
    _add_status(conn, device_id, 1000, 601, AIRTHINGS_STATUS)

    def unavailable(_message: str) -> str:
        raise RuntimeError("Slack unavailable")

    result = rules_engine.run_alert_rules(
        conn, when=1600, commit=True, notifier=unavailable
    )

    assert result == f"Device {device_id} triggered SensorStuck"
    event = conn.execute(
        """
        SELECT event_type, slack_status, slack_error, slack_attempt_count,
               slack_last_attempt_time, slack_next_attempt_time, slack_terminal
        FROM alert_events
        """
    ).fetchone()
    assert tuple(event) == (
        "triggered",
        "failed",
        "Slack unavailable",
        1,
        1600,
        1660,
        0,
    )
    assert db_alerts.get_active_alert_record(conn, device_id, "SensorStuck") is not None


def test_pending_alert_event_is_delivered_after_process_restart(test_database_conn):
    conn = test_database_conn
    device_id = _add_airthings_device(conn)
    alert = db_alerts.create_alert_record(
        conn,
        device_id=device_id,
        alert_type="SensorStuck",
        start_time=1000,
    )
    event = db_alerts.create_alert_event(
        conn,
        alert_id=alert.alert_id,
        event_time=1600,
        event_type=AlertEventType.TRIGGERED,
        message="Airthings Dungeon is stuck",
    )
    conn.commit()
    delivered: list[str] = []

    result = rules_engine.run_alert_rules(
        conn,
        when=1600,
        commit=True,
        notifier=lambda message: delivered.append(message) or "message-1",
    )

    assert result == ""
    assert delivered == ["Airthings Dungeon is stuck"]
    stored = db_alerts.get_latest_alert_event(conn, alert.alert_id)
    assert stored is not None
    assert stored.alert_event_id == event.alert_event_id
    assert stored.slack_status.value == "sent"
    assert stored.slack_attempt_count == 1
    assert stored.slack_last_attempt_time == 1600
    assert stored.slack_next_attempt_time is None
    assert stored.slack_terminal is True


def test_failed_recovery_delivery_retries_after_alert_is_closed(test_database_conn):
    conn = test_database_conn
    device_id = _add_airthings_device(conn)
    _add_status(conn, device_id, 1000, 601, AIRTHINGS_STATUS)
    assert rules_engine.run_alert_rules(
        conn, when=1600, commit=True, notifier=lambda _message: "triggered-ts"
    )
    changed = {**AIRTHINGS_STATUS, "co2": {"unit": "ppm", "value": 499.0}}
    _add_status(conn, device_id, 1601, 1, changed)

    def unavailable(_message: str) -> str:
        raise RuntimeError("Slack unavailable")

    result = rules_engine.run_alert_rules(
        conn, when=1601, commit=True, notifier=unavailable
    )
    assert result == f"Device {device_id} resolved SensorStuck"
    assert db_alerts.get_active_alert_record(conn, device_id, "SensorStuck") is None

    delivered: list[str] = []
    rules_engine.run_alert_rules(
        conn,
        when=1660,
        commit=True,
        notifier=lambda message: delivered.append(message) or "too-early",
    )
    assert not delivered
    rules_engine.run_alert_rules(
        conn,
        when=1661,
        commit=True,
        notifier=lambda message: delivered.append(message) or "resolved-ts",
    )

    assert len(delivered) == 1
    assert "is unstuck" in delivered[0]
    recovery = conn.execute(
        """
        SELECT slack_status, slack_message_ts, slack_attempt_count,
               slack_next_attempt_time, slack_terminal
        FROM alert_events
        WHERE event_type='resolved'
        """
    ).fetchone()
    assert tuple(recovery) == ("sent", "resolved-ts", 2, None, 1)


def test_slack_retry_after_extends_delivery_backoff(test_database_conn):
    conn = test_database_conn
    device_id = _add_airthings_device(conn)
    alert = db_alerts.create_alert_record(
        conn,
        device_id=device_id,
        alert_type="SensorStuck",
        start_time=1000,
    )
    db_alerts.create_alert_event(
        conn,
        alert_id=alert.alert_id,
        event_time=1600,
        event_type=AlertEventType.TRIGGERED,
        message="rate limited alert",
    )
    conn.commit()
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "600"

    def rate_limited(_message: str) -> str:
        raise requests.exceptions.HTTPError(response=response)

    rules_engine.run_alert_rules(
        conn, when=1600, commit=True, notifier=rate_limited
    )

    event = db_alerts.get_latest_alert_event(conn, alert.alert_id)
    assert event is not None
    assert event.slack_status.value == "failed"
    assert event.slack_attempt_count == 1
    assert event.slack_next_attempt_time == 2200
    assert event.slack_terminal is False


def test_delivery_stops_after_retry_limit(test_database_conn):
    conn = test_database_conn
    device_id = _add_airthings_device(conn)
    alert = db_alerts.create_alert_record(
        conn,
        device_id=device_id,
        alert_type="SensorStuck",
        start_time=1000,
    )
    event = db_alerts.create_alert_event(
        conn,
        alert_id=alert.alert_id,
        event_time=1600,
        event_type=AlertEventType.TRIGGERED,
        message="terminal alert",
    )
    conn.execute(
        "UPDATE alert_events SET slack_attempt_count=? WHERE alert_event_id=?",
        (rules_engine.ALERT_DELIVERY_MAX_ATTEMPTS - 1, event.alert_event_id),
    )
    conn.commit()

    def unavailable(_message: str) -> str:
        raise RuntimeError("Slack unavailable")

    rules_engine.run_alert_rules(
        conn, when=1600, commit=True, notifier=unavailable
    )
    stored = db_alerts.get_latest_alert_event(conn, alert.alert_id)
    assert stored is not None
    assert stored.slack_status.value == "failed"
    assert stored.slack_attempt_count == rules_engine.ALERT_DELIVERY_MAX_ATTEMPTS
    assert stored.slack_next_attempt_time is None
    assert stored.slack_terminal is True
    db_alerts.resolve_alert_record(conn, alert.alert_id, end_time=1601)
    conn.commit()

    delivered: list[str] = []
    rules_engine.run_alert_rules(
        conn,
        when=100_000,
        commit=True,
        notifier=lambda message: delivered.append(message) or "unexpected",
    )
    assert not delivered
