"""Stateful monitoring-rule tests using the real SQLite schema and rules file."""

import json

from app import db, db_alerts, rules_engine


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


def _add_airthings_device(conn, name: str = "Airthings Dungeon") -> int:
    cursor = conn.execute(
        """
        INSERT INTO devices (device_name, device_type, aqi_mon)
        VALUES (?, 'SENSOR', 1)
        """,
        (name,),
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


def test_exact_value_run_crosses_rle_rows_and_ignores_key_order(test_database_conn):
    conn = test_database_conn
    device_id = _add_airthings_device(conn)
    prior = {**AIRTHINGS_STATUS, "co2": {"unit": "ppm", "value": 497.0}}
    _add_status(conn, device_id, 900, 100, prior)
    _add_status(conn, device_id, 1000, 1200, AIRTHINGS_STATUS)
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
        "SELECT event_type, slack_status, slack_error FROM alert_events"
    ).fetchone()
    assert tuple(event) == ("triggered", "failed", "Slack unavailable")
    assert db_alerts.get_active_alert_record(conn, device_id, "SensorStuck") is not None
