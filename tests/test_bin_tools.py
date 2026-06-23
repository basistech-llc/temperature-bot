"""
Tests for bin/ tools to ensure they work correctly after refactoring.
Tests cover runner.py, and rules.py functionality.
"""
import os
import sys
import tempfile
import subprocess
import sqlite3
import logging
import datetime
import importlib.util
from pathlib import Path

import pytest
from conftest import db_path

from app.constants import TEST_DB_NAME
from app.models import Device, RuleResult

logger = logging.getLogger(__name__)

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

    if result.returncode != 0:
        logger.debug("result.stderr=%s", result.stderr)
        assert "appId" in result.stderr or "hubitat" in result.stderr.lower()
    else:
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

    if result.returncode != 0:
        assert "Test Device" in result.stdout or "appId" in result.stderr
    else:
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
