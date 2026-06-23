"""
Tests for the master rules kill switch behaviour.
"""

import datetime
import time
from unittest.mock import patch

from app import db
from app import rules_engine


def _add_rule_test_erv(conn):
    device_id = db.get_or_create_device_id(conn, "ERV Kitchen", use_cache=False)
    now = int(time.time())
    conn.execute("INSERT INTO aqi (logtime, aqi) VALUES (?, ?)", (now, 45))
    conn.execute(
        """
        INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            device_id,
            now,
            60,
            240,
            '{"Drive": "ON", "FanSpeed": "LOW", "InletTemp": "24.0"}',
        ),
    )
    conn.commit()
    return device_id


def test_run_rules_respects_master_switch(test_database_conn_with_test_data):
    """run_rules should completely skip rule execution when the master switch is OFF."""
    conn = test_database_conn_with_test_data[0]

    # Ensure master is OFF
    db.set_rules_master_enabled(conn, False)
    assert db.get_rules_master_enabled(conn) is False

    # When master is OFF, run_rules should return early and never exec any rules.
    with patch("app.rules_engine.get_rules") as mock_get_rules:
        rules_engine.run_all_rules(conn)
        mock_get_rules.assert_not_called()

    # Turn master back ON
    db.set_rules_master_enabled(conn, True)
    assert db.get_rules_master_enabled(conn) is True

    # When master is ON, run_rules should attempt to load rules (and thus call get_rules).
    with patch("app.rules_engine.get_rules") as mock_get_rules:
        # Return a no-op rules script; we only care that it was requested.
        mock_get_rules.return_value = "pass\n"
        rules_engine.run_all_rules(conn, when=time.time())
        mock_get_rules.assert_called_once()


def test_get_last_aqi_defaults_to_50_when_empty(test_database_conn):
    """Rules should have a conservative AQI value before the first AQI poll."""
    assert db.get_last_aqi(test_database_conn) == 50


def test_run_all_rules_respects_global_time_suspension(test_database_conn):
    """run_all_rules owns the rules_engine time-limited suspension check."""
    conn = test_database_conn
    rules_engine.disable_all_rules(conn, 600)

    with patch("app.rules_engine.get_rules") as mock_get_rules:
        assert (
            rules_engine.run_all_rules(conn)
            == rules_engine.RULES_TIME_SUSPENDED_MESSAGE
        )
        mock_get_rules.assert_not_called()


def test_rules_results_runs_device_rule_contract(test_database_conn, monkeypatch):
    """rules_results should dry-run the new per-device rule function."""
    conn = test_database_conn
    device_id = _add_rule_test_erv(conn)

    monkeypatch.setattr(
        rules_engine,
        "get_rules",
        lambda: (
            "from app.models import RuleResult\n"
            "def run_rules_for_device(device, now, aqi):\n"
            "    if device.erv and now.hour == 11 and aqi == 75:\n"
            "        return RuleResult(fan_speed='High', drive='on')\n"
            "    return None\n"
        ),
    )

    when = datetime.datetime(2026, 6, 23, 11, 0).timestamp()
    assert rules_engine.rules_results(conn, when=when, aqi=75) == (
        f"Device {device_id} drive set to 1\n"
        f"Device {device_id} speed set to 4"
    )


def test_run_all_rules_uses_supplied_when(test_database_conn, monkeypatch):
    """run_all_rules should pass the requested evaluation time into rules."""
    conn = test_database_conn
    device_id = _add_rule_test_erv(conn)

    monkeypatch.setattr(
        rules_engine,
        "get_rules",
        lambda: (
            "from app.models import RuleResult\n"
            "def run_rules_for_device(device, now, aqi):\n"
            "    if device.erv and now.hour == 22:\n"
            "        return RuleResult(drive='on')\n"
            "    return None\n"
        ),
    )

    when = datetime.datetime(2026, 6, 23, 22, 0).timestamp()
    assert f"Device {device_id} drive set to 1" in rules_engine.run_all_rules(
        conn, when=when
    )
