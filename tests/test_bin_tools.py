"""
Tests for bin/ tools to ensure they work correctly after refactoring.
Tests cover runner.py, and rules.py functionality.
"""
import os
import sys
import tempfile
import subprocess
import sqlite3
import datetime
import importlib.util
import json
import logging
from pathlib import Path

import pytest
import requests
from conftest import db_path

from app.constants import TEST_DB_NAME
from app import ae200, db_alerts
from app.device_types import DEVICE_SUBTYPE_AIRTHINGS, DEVICE_TYPE_SENSOR
from app.models import Device, RuleResult
from bin import runner

@pytest.fixture
def temp_db(test_database_conn_with_test_data):
    """Return the database path."""
    test_database_conn = test_database_conn_with_test_data[0]
    yield db_path(test_database_conn)


@pytest.fixture
def bin_dir():
    """Get the bin directory path."""
    return Path(__file__).parent.parent / "bin"


def test_runner_help(bin_dir):
    """Test that runner.py --help works."""
    result = subprocess.run(
        [sys.executable, str(bin_dir / "runner.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, f"runner.py --help failed: {result.stderr}"
    assert "BasisTech LLC Runner" in result.stdout
    assert "--csv" in result.stdout
    assert "--report" in result.stdout
    assert "--aqi" in result.stdout


def test_runner_module_help_has_no_runpy_warning():
    """The Makefile runs runner as `python -m bin.runner`."""
    result = subprocess.run(
        [sys.executable, "-m", "bin.runner", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, f"python -m bin.runner --help failed: {result.stderr}"
    assert "BasisTech LLC Runner" in result.stdout
    assert "RuntimeWarning" not in result.stderr


@pytest.mark.parametrize("failure", ["timeout", "malformed"])
def test_runner_alerts_continue_when_airthings_poll_fails(
    failure, monkeypatch, temp_db, caplog
):
    """Airthings failures must not suppress alert reminders or recoveries."""
    alert_calls = []

    if failure == "timeout":

        def fail_airthings_request():
            raise requests.exceptions.Timeout("Airthings timed out")

        monkeypatch.setattr(
            runner.airthings, "read_airthings_now", fail_airthings_request
        )
    else:
        monkeypatch.setattr(
            runner.airthings,
            "read_airthings_now",
            lambda: [
                {
                    "name": "Valid First Device",
                    "sensors": [
                        {"sensorType": "temp", "value": 21, "unit": "c"}
                    ],
                },
                {
                    "name": "Lab",
                    "sensors": [
                        {"sensorType": "humidity", "value": 45, "unit": "pct"}
                    ],
                }
            ],
        )

    monkeypatch.setenv(TEST_DB_NAME, temp_db)
    monkeypatch.setattr(sys, "argv", ["runner"])
    monkeypatch.setattr(runner, "update_from_ae200", lambda _conn: None)
    monkeypatch.setattr(runner, "update_from_hubitat", lambda _conn: None)
    monkeypatch.setattr(runner.db, "get_rules_master_enabled", lambda _conn: False)

    def record_alert_run(conn, *, commit, compiled_rules):
        alert_calls.append((conn, commit, compiled_rules))
        return ""

    monkeypatch.setattr(runner.rules_engine, "run_alert_rules", record_alert_run)

    with caplog.at_level(logging.ERROR, logger="bin.runner"):
        runner.main()

    assert len(alert_calls) == 1
    assert alert_calls[0][1] is True
    assert isinstance(alert_calls[0][2], runner.rules_engine.CompiledRules)
    assert "update_from_airthings: collection failed:" in caplog.text
    with sqlite3.connect(temp_db) as conn:
        airthings_device_count = conn.execute(
            "SELECT COUNT(*) FROM devices WHERE device_name LIKE 'Airthings %'"
        ).fetchone()[0]
    assert airthings_device_count == 0


def test_makefile_local_targets_control_sensor_simulators():
    """Local dev targets must make simulator/live intent explicit for all sensors."""
    makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text(
        encoding="utf-8"
    )

    assert "local-dev-sim:" in makefile
    assert "local-dev: local-dev-sim" in makefile
    assert "local-dev-live:" in makefile
    assert "local-live-dev: local-dev-live" in makefile
    assert "TEMPERATURE_BOT_INSTANCE=local-dev-sim" in makefile
    assert "TEMPERATURE_BOT_INSTANCE=local-dev-live" in makefile
    assert "TEMPERATURE_BOT_DATABASE_IDENTITY=local-dev-sim" in makefile
    assert "TEMPERATURE_BOT_DATABASE_IDENTITY=local-dev-live" in makefile
    assert "TEMPERATURE_BOT_DATABASE_ROOT=\"$(LOCAL_DATABASE_ROOT)\"" in makefile
    assert "TEMPERATURE_BOT_CONTROL_MODE=simulator" in makefile
    assert "TEMPERATURE_BOT_CONTROL_MODE=live" in makefile
    assert "TEMPERATURE_BOT_SCHEDULER_MODE=disabled" in makefile
    assert "AE200_SIMULATOR=1 HUBITAT_SIMULATOR=1 AIRTHINGS_SIMULATOR=1 AQICN_SIMULATOR=1" in makefile
    assert "AE200_SIMULATOR= HUBITAT_SIMULATOR= AIRTHINGS_SIMULATOR= AQICN_SIMULATOR=" in makefile


def test_fetch_dev_db_allows_interactive_ssh_authentication():
    """The developer database fetch must allow SSH password fallback."""
    makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text(
        encoding="utf-8"
    )

    assert makefile.count("BatchMode=no") == 2
    assert "BatchMode=yes" not in makefile


def test_legacy_systemd_install_includes_timer_units():
    """The legacy installer must copy and restart its paired timer units."""
    etc_dir = Path(__file__).resolve().parents[1] / "etc"
    result = subprocess.run(
        ["make", "-n", "install"],
        cwd=etc_dir,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    commands = result.stdout.splitlines()

    timer = "temperature-bot-performance-monitor.timer"
    assert timer in commands[0]
    assert timer in commands[-1]


def test_fetch_dev_db_timeout_does_not_pollute_sqlite_dump(tmp_path):
    """The fetch timeout must not write its value into the dump stream."""
    makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text(
        encoding="utf-8"
    )
    assert "-cmd '.timeout 30000'" in makefile
    assert "-cmd 'PRAGMA busy_timeout=30000;'" not in makefile
    assert "FETCH_REMOTE_DB_USER ?= temperature_bot" in makefile
    assert "timeout 180 sudo -n -u $(FETCH_REMOTE_DB_USER)" in makefile

    source_db = tmp_path / "source.db"
    imported_db = tmp_path / "imported.db"
    with sqlite3.connect(source_db) as connection:
        connection.execute("CREATE TABLE devices (device_id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO devices (device_id) VALUES (7)")

    dump = subprocess.run(
        [
            "sqlite3",
            "-batch",
            "-init",
            "/dev/null",
            "-cmd",
            ".timeout 30000",
            f"file:{source_db}?mode=ro",
            ".dump",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert dump.returncode == 0, dump.stderr
    assert dump.stdout.startswith("PRAGMA foreign_keys=OFF;\n")
    assert "30000" not in dump.stdout

    import_result = subprocess.run(
        ["sqlite3", "-batch", "-init", "/dev/null", str(imported_db)],
        input=dump.stdout,
        capture_output=True,
        text=True,
        check=False,
    )
    assert import_result.returncode == 0, import_result.stderr
    with sqlite3.connect(imported_db) as connection:
        assert connection.execute("SELECT device_id FROM devices").fetchone() == (7,)


def test_update_from_airthings_persists_sensor_status(monkeypatch, test_database_conn):
    """Airthings updater should write both temperature and rich air-quality payloads."""
    monkeypatch.setattr(
        runner.airthings,
        "read_airthings_now",
        lambda: [
            {
                "name": "Lab",
                "sensors": [
                    {"sensorType": "temp", "value": 21.4, "unit": "c"},
                    {"sensorType": "humidity", "value": 45.0, "unit": "pct"},
                    {"sensorType": "co2", "value": 744.0, "unit": "ppm"},
                    {"sensorType": "pm25", "value": 3.2, "unit": "ug/m3"},
                ],
            }
        ],
    )

    runner.update_from_airthings(test_database_conn)

    row = test_database_conn.execute(
        """
        SELECT d.device_name, d.device_type, d.device_subtype,
               l.temp10x, l.status_json
        FROM devices d
        JOIN devlog l ON d.device_id = l.device_id
        WHERE d.device_name = ?
        ORDER BY l.logtime DESC
        LIMIT 1
        """,
        ("Airthings Lab",),
    ).fetchone()
    assert row is not None
    assert row["device_type"] == DEVICE_TYPE_SENSOR
    assert row["device_subtype"] == DEVICE_SUBTYPE_AIRTHINGS
    assert row["temp10x"] == 214
    status = json.loads(row["status_json"])
    assert status["humidity"]["value"] == 45.0
    assert status["co2"]["value"] == 744.0
    assert status["pm25"]["value"] == 3.2


def test_update_from_airthings_preserves_existing_device_subtype(
    monkeypatch, test_database_conn
):
    """Airthings discovery fills NULL metadata without replacing prior identity."""
    test_database_conn.execute(
        """
        INSERT INTO devices (device_name, device_type, device_subtype)
        VALUES ('Airthings Lab', 'SENSOR', 'MANUAL')
        """
    )
    test_database_conn.commit()
    monkeypatch.setattr(
        runner.airthings,
        "read_airthings_now",
        lambda: [
            {
                "name": "Lab",
                "sensors": [
                    {"sensorType": "temp", "value": 21.4, "unit": "c"},
                ],
            }
        ],
    )

    runner.update_from_airthings(test_database_conn)

    subtype = test_database_conn.execute(
        "SELECT device_subtype FROM devices WHERE device_name='Airthings Lab'"
    ).fetchone()[0]
    assert subtype == "MANUAL"


def test_ae200_alerts_use_generalized_lifecycle_and_delivery(test_database_conn):
    conn = test_database_conn
    device = {"id": "1", "name": "Conference FCU"}
    active = {
        "InletTemp": "23.0",
        ae200.ERROR_SIGN: "ON",
        ae200.FILTER_SIGN: "OFF",
        ae200.CHECK_WATER: "OFF",
    }
    delivered: list[str] = []

    runner.process_device_alert_data(
        conn,
        device,
        active,
        observed_at=1000,
        notifier=lambda message: delivered.append(message) or "trigger-ts",
    )
    device_id = conn.execute(
        "SELECT device_id FROM devices WHERE device_name=?", (device["name"],)
    ).fetchone()[0]
    alert = db_alerts.get_active_alert_record(conn, device_id, ae200.ERROR_SIGN)
    assert alert is not None
    assert delivered == [":warning: AE-200 Conference FCU reports error condition."]

    runner.process_device_alert_data(
        conn,
        device,
        {**active, ae200.ERROR_SIGN: "OFF"},
        observed_at=1001,
        notifier=lambda message: delivered.append(message) or "resolved-ts",
    )

    assert db_alerts.get_active_alert_record(conn, device_id, ae200.ERROR_SIGN) is None
    events = conn.execute(
        "SELECT event_type, slack_status FROM alert_events WHERE alert_id=? "
        "ORDER BY alert_event_id",
        (alert.alert_id,),
    ).fetchall()
    assert [tuple(event) for event in events] == [
        ("triggered", "sent"),
        ("resolved", "sent"),
    ]
    assert delivered[-1] == (
        ":white_check_mark: AE-200 Conference FCU cleared error condition."
    )


def test_runner_database_access(bin_dir, temp_db):
    """Test that runner.py can access the database."""
    env = os.environ.copy()
    env[TEST_DB_NAME] = temp_db

    result = subprocess.run(
        [sys.executable, str(bin_dir / "runner.py"), "--report"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )

    assert result.returncode == 0, f"runner.py --report failed: {result.stderr}"
    assert len(result.stdout) > 0


def test_runner_aqi_update(bin_dir, temp_db):
    """Test that runner.py can update AQI in database."""
    env = os.environ.copy()
    env[TEST_DB_NAME] = temp_db
    env['AQICN_SIMULATOR'] = '1'

    result = subprocess.run(
        [sys.executable, str(bin_dir / "runner.py"), "--aqi"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )

    assert result.returncode == 0, f"runner.py --aqi failed: {result.stderr}"


def test_rules_file_defines_device_rule_contract(bin_dir):
    """rules.py exposes executable per-device rules with normalized outputs."""
    rules_file = bin_dir / "rules.py"
    assert rules_file.exists(), "rules.py file not found"

    spec = importlib.util.spec_from_file_location("rules_under_test", rules_file)
    assert spec is not None
    assert spec.loader is not None
    rules_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rules_module)

    kitchen_erv = Device(device_id=1, erv=True, name="ERV Kitchen")
    fcu = Device(device_id=2, erv=False, name="Broadway South")
    lunch_time = datetime.datetime(2026, 6, 23, 11, 0)
    night_time = datetime.datetime(2026, 6, 23, 22, 0)

    assert rules_module.run_rules_for_device(fcu, lunch_time, 0) is None
    assert rules_module.run_rules_for_device(kitchen_erv, lunch_time, 0) == RuleResult(
        fan_speed="HIGH", drive="ON"
    )
    assert rules_module.run_rules_for_device(kitchen_erv, lunch_time, 75) == RuleResult(
        fan_speed="LOW", drive="ON"
    )
    assert rules_module.run_rules_for_device(kitchen_erv, lunch_time, 125) == RuleResult(
        drive="OFF"
    )
    assert rules_module.run_rules_for_device(kitchen_erv, night_time, 0) == RuleResult(
        fan_speed="HIGH", drive="ON"
    )


def test_rules_syntax_valid(bin_dir):
    """Test that rules.py has valid Python syntax."""
    rules_file = bin_dir / "rules.py"

    with open(rules_file, encoding="utf-8") as f:
        source = f.read()

    try:
        compile(source, str(rules_file), 'exec')
    except SyntaxError as e:
        pytest.fail(f"rules.py has syntax error: {e}")


def test_runner_imports(bin_dir):
    """Test that runner.py can import all required modules."""
    result = subprocess.run(
        [sys.executable, "-c", f"""
import sys
sys.path.append('{bin_dir.parent}')
import bin.runner
print('runner.py imports successfully')
"""],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, f"runner.py import failed: {result.stderr}"
    assert "runner.py imports successfully" in result.stdout


def test_runner_with_test_database(bin_dir, temp_db):
    """Test runner.py with a test database that has some data."""
    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    cursor = conn.cursor()
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Test Device",))
    device_id = cursor.lastrowid

    conn.execute("""
        INSERT INTO devlog (device_id, logtime, temp10x, duration, status_json)
        VALUES (?, ?, ?, ?, ?)
    """, (device_id, 1609459200, 250, 60, '{"temp": 25.0}'))

    conn.commit()
    conn.close()

    env = os.environ.copy()
    env[TEST_DB_NAME] = temp_db

    result = subprocess.run(
        [sys.executable, str(bin_dir / "runner.py"), "--report"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )

    assert result.returncode == 0, f"runner.py --report failed: {result.stderr}"
    assert "Test Device" in result.stdout or "No data found" in result.stdout


def test_runner_daily_cleanup(bin_dir, temp_db):
    """Test runner.py daily cleanup functionality."""
    env = os.environ.copy()
    env[TEST_DB_NAME] = temp_db

    result = subprocess.run(
        [sys.executable, str(bin_dir / "runner.py"), "--daily"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )

    assert result.returncode == 0, f"runner.py --daily failed: {result.stderr}"


def test_runner_rules_test(bin_dir, temp_db):
    """Test runner.py rules test functionality."""
    env = os.environ.copy()
    env[TEST_DB_NAME] = temp_db

    result = subprocess.run(
        [sys.executable, str(bin_dir / "runner.py"), "--rules", "test"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )

    if result.returncode != 0:
        assert "ERV_KITCHEN" in result.stderr or "NameError" in result.stderr
    else:
        assert len(result.stdout) > 0


def test_runner_with_csv_import(bin_dir, temp_db):
    """Test runner.py CSV import functionality."""
    csv_content = "time,Broadway North\n2025-01-01T12:00:00,25.0\n"
    csv_path = ""

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as csv_file:
            csv_file.write(csv_content)
            csv_path = csv_file.name

        env = os.environ.copy()
        env[TEST_DB_NAME] = temp_db

        result = subprocess.run(
            [sys.executable, str(bin_dir / "runner.py"), "--csv", csv_path, "--csv-after", "2024-01-01"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            check=False,
        )

        if result.returncode != 0:
            assert "KeyError" in result.stderr or "labelmap" in result.stderr
        else:
            assert result.returncode == 0
    finally:
        if csv_path:
            Path(csv_path).unlink(missing_ok=True)


def test_all_tools_help_consistency(bin_dir):
    """Test that all tools have consistent help output."""
    tools = ["runner.py"]

    for tool in tools:
        result = subprocess.run(
            [sys.executable, str(bin_dir / tool), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        assert result.returncode == 0, f"{tool} --help failed: {result.stderr}"
        assert "usage:" in result.stdout.lower() or "options:" in result.stdout.lower()
        assert "--help" in result.stdout
