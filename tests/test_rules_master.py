"""
Tests for the master rules kill switch behaviour.
"""

import datetime
import logging
import time
from unittest.mock import patch

from app import db
from app import rules_engine
from app.constants import RESERVED_DEVICE_NAMES


def _add_rule_test_erv(
    conn, *, name: str = "ERV Kitchen", observed_at: int | None = None
):
    device_id = db.get_or_create_device_id(conn, name, use_cache=False)
    now = observed_at if observed_at is not None else int(time.time())
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


def test_get_last_aqi_preserves_value_and_timestamp(test_database_conn):
    assert db.get_last_aqi(test_database_conn) is None
    test_database_conn.execute("INSERT INTO aqi (logtime, aqi) VALUES (1000, 62)")
    observation = db.get_last_aqi(test_database_conn)
    assert observation is not None
    assert observation.value == 62
    assert observation.observed_at == 1000


def test_run_all_rules_rejects_missing_stale_and_future_aqi(test_database_conn):
    conn = test_database_conn
    now = 10_000
    assert rules_engine.run_all_rules(conn, when=now) == rules_engine.AQI_MISSING_MESSAGE

    conn.execute("INSERT INTO aqi (logtime, aqi) VALUES (?, 62)", (now - 7201,))
    conn.commit()
    assert rules_engine.run_all_rules(conn, when=now) == rules_engine.AQI_STALE_MESSAGE

    conn.execute("INSERT INTO aqi (logtime, aqi) VALUES (?, 62)", (now + 1,))
    conn.commit()
    assert rules_engine.run_all_rules(conn, when=now) == rules_engine.AQI_FUTURE_MESSAGE


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


def test_run_all_rules_dry_run_does_not_mutate_database(
    test_database_conn, monkeypatch
):
    """commit=False should not create pseudo-devices or clear expired timers."""
    conn = test_database_conn
    device_id = _add_rule_test_erv(conn)
    expired_until = int(time.time()) - 60
    conn.execute(
        "UPDATE devices SET disabled_until=? WHERE device_id=?",
        (expired_until, device_id),
    )
    conn.commit()

    changelog_count = conn.execute("SELECT COUNT(*) FROM changelog").fetchone()[0]
    pseudo_count = conn.execute(
        """
        SELECT COUNT(*) FROM devices
        WHERE device_name IN (?, ?)
        """,
        tuple(RESERVED_DEVICE_NAMES),
    ).fetchone()[0]
    assert pseudo_count == 0

    monkeypatch.setattr(
        rules_engine,
        "get_rules",
        lambda: "def run_rules_for_device(device, now, aqi):\n    return None\n",
    )

    rules_engine.run_all_rules(conn, commit=False)

    disabled_until = conn.execute(
        "SELECT disabled_until FROM devices WHERE device_id=?",
        (device_id,),
    ).fetchone()["disabled_until"]
    assert disabled_until == expired_until
    final_changelog_count = conn.execute(
        "SELECT COUNT(*) FROM changelog"
    ).fetchone()[0]
    assert final_changelog_count == changelog_count
    assert (
        conn.execute(
            """
            SELECT COUNT(*) FROM devices
            WHERE device_name IN (?, ?)
            """,
            tuple(RESERVED_DEVICE_NAMES),
        ).fetchone()[0]
        == 0
    )


def test_run_all_rules_compile_failure_logs_traceback(
    test_database_conn, monkeypatch, caplog
):
    """Broken rules.py compilation should preserve traceback details in logs."""
    conn = test_database_conn
    now = int(time.time())
    conn.execute("INSERT INTO aqi (logtime, aqi) VALUES (?, 45)", (now,))
    conn.commit()
    monkeypatch.setattr(
        rules_engine,
        "get_rules",
        lambda: "def run_rules_for_device(:\n    return None\n",
    )

    with caplog.at_level(logging.ERROR, logger="app.rules_engine"):
        result = rules_engine.run_all_rules(conn, commit=False)

    assert result == "Cannot compile rules"
    assert "Failed to compile rules from" in caplog.text
    assert any(record.exc_info for record in caplog.records)


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
        f"Device {device_id} drive set to ON\n"
        f"Device {device_id} speed set to HIGH"
    )


def test_compiled_rules_are_shared_across_entry_points(
    test_database_conn, monkeypatch
):
    """Alert, action, and forecast passes reuse one execution of rules.py."""
    conn = test_database_conn
    device_id = _add_rule_test_erv(conn)
    compile_count = 0

    def rules_source():
        nonlocal compile_count
        compile_count += 1
        return (
            "from app.models import RuleResult\n"
            "def run_alert_rules_for_device(device, now):\n"
            "    return []\n"
            "def run_rules_for_device(device, now, aqi):\n"
            "    return RuleResult(drive='on') if device.erv else None\n"
        )

    monkeypatch.setattr(rules_engine, "get_rules", rules_source)
    compiled = rules_engine.compile_rules()

    assert rules_engine.run_alert_rules(conn, compiled_rules=compiled) == ""
    assert f"Device {device_id} drive set to ON" in rules_engine.run_all_rules(
        conn, compiled_rules=compiled
    )
    assert rules_engine.rules_results(conn, compiled_rules=compiled) == (
        f"Device {device_id} drive set to ON"
    )
    assert rules_engine.rules_results(conn, aqi=75, compiled_rules=compiled) == (
        f"Device {device_id} drive set to ON"
    )
    assert compile_count == 1


def test_run_all_rules_uses_supplied_when(test_database_conn, monkeypatch):
    """run_all_rules should pass the requested evaluation time into rules."""
    conn = test_database_conn
    when = datetime.datetime(2026, 6, 23, 22, 0).timestamp()
    device_id = _add_rule_test_erv(conn, observed_at=int(when))

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

    assert f"Device {device_id} drive set to ON" in rules_engine.run_all_rules(
        conn, when=when
    )


def test_run_all_rules_skips_devices_when_rules_disabled(
    test_database_conn, monkeypatch
):
    """Permanent per-device rules_enabled=false should suppress rule execution."""
    conn = test_database_conn
    device_id = _add_rule_test_erv(conn)
    conn.execute(
        "UPDATE devices SET rules_enabled=0 WHERE device_id=?",
        (device_id,),
    )
    conn.commit()

    monkeypatch.setattr(
        rules_engine,
        "get_rules",
        lambda: (
            "from app.models import RuleResult\n"
            "def run_rules_for_device(device, now, aqi):\n"
            "    return RuleResult(drive='on')\n"
        ),
    )

    result = rules_engine.run_all_rules(conn)
    assert f"Device {device_id} rules are disabled" in result
    assert f"Device {device_id} drive set to ON" not in result


def test_run_all_rules_isolates_device_failures(test_database_conn, monkeypatch):
    """A broken device rule must not prevent later devices from being evaluated."""
    conn = test_database_conn
    broken_id = _add_rule_test_erv(conn, name="ERV Broken")
    healthy_id = _add_rule_test_erv(conn, name="ERV Healthy")
    monkeypatch.setattr(
        rules_engine,
        "get_rules",
        lambda: (
            "from app.models import RuleResult\n"
            "def run_rules_for_device(device, now, aqi):\n"
            "    if device.name == 'ERV Broken':\n"
            "        raise RuntimeError('bad device rule')\n"
            "    return RuleResult(drive='on')\n"
        ),
    )

    result = rules_engine.run_all_rules(conn, commit=False)

    assert (
        f"Device {broken_id} action-rule failure: RuntimeError: bad device rule"
        in result
    )
    assert f"Device {healthy_id} drive set to ON" in result


def test_run_all_rules_audits_committed_device_failure(
    test_database_conn, monkeypatch
):
    """Committed action passes retain a durable record of per-device failures."""
    conn = test_database_conn
    device_id = _add_rule_test_erv(conn, name="ERV Broken")
    monkeypatch.setattr(
        rules_engine,
        "get_rules",
        lambda: (
            "def run_rules_for_device(device, now, aqi):\n"
            "    raise ValueError('invalid device state')\n"
        ),
    )

    result = rules_engine.run_all_rules(conn, commit=True)
    row = conn.execute(
        """
        SELECT new_value, agent, comment
        FROM changelog
        WHERE device_id=?
        ORDER BY changelog_id DESC
        LIMIT 1
        """,
        (device_id,),
    ).fetchone()

    assert f"Device {device_id} action-rule failure: ValueError" in result
    assert dict(row) == {
        "new_value": "ValueError",
        "agent": "rules runner",
        "comment": "action-rule failure: invalid device state",
    }
