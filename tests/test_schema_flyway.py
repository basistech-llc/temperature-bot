"""Flyway schema tests."""

from contextlib import closing
import sqlite3
from pathlib import Path

import pytest

from app import db
from app.constants import DB_PATH, TEST_DB_NAME
from app.paths import ROOT_DIR, SCHEMA_FILE_PATH
from bin import runner

BASELINE_APP_TABLES = {"devices", "devlog", "changelog", "aqi", "alerts"}
MIGRATED_APP_TABLES = BASELINE_APP_TABLES | {
    "rooms",
    "fcu_temp_sources",
    "fcu_set_ranges",
}
BASELINE_MIGRATION_PATH = (
    Path(ROOT_DIR) / "etc" / "flyway" / "sql" / "V1__baseline_schema.sql"
)
MIGRATION_DIR = Path(ROOT_DIR) / "etc" / "flyway" / "sql"


def table_names_created_by(sql_path):
    with closing(sqlite3.connect(":memory:")) as conn:
        with open(sql_path, "r", encoding="utf-8") as schema_file:
            conn.executescript(schema_file.read())
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }


def index_names_created_by(sql_path):
    with closing(sqlite3.connect(":memory:")) as conn:
        with open(sql_path, "r", encoding="utf-8") as schema_file:
            conn.executescript(schema_file.read())
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
            )
        }


def test_schema_file_contains_application_tables_only():
    tables = table_names_created_by(SCHEMA_FILE_PATH)
    assert MIGRATED_APP_TABLES <= tables
    assert "flyway_schema_history" not in tables


def test_schema_file_can_be_applied_twice():
    """The generated compatibility schema must remain idempotent."""
    with closing(sqlite3.connect(":memory:")) as conn:
        schema_sql = Path(SCHEMA_FILE_PATH).read_text(encoding="utf-8")
        conn.executescript(schema_sql)
        conn.executescript(schema_sql)


def test_baseline_migration_does_not_create_flyway_history_table():
    tables = table_names_created_by(BASELINE_MIGRATION_PATH)
    assert BASELINE_APP_TABLES <= tables
    assert "rooms" not in tables
    assert "fcu_temp_sources" not in tables
    assert "fcu_set_ranges" not in tables
    assert "flyway_schema_history" not in tables


def test_baseline_migration_matches_deployed_changelog_device_index():
    indexes = index_names_created_by(BASELINE_MIGRATION_PATH)
    assert "idx_changelog_device_id" in indexes
    assert "idx_changelog_device_id_logtime" not in indexes


def test_schema_file_contains_migrated_changelog_device_logtime_index():
    indexes = index_names_created_by(SCHEMA_FILE_PATH)
    assert "idx_changelog_device_id_logtime" in indexes
    assert "idx_changelog_device_id" not in indexes
    assert "idx_rooms_fcu_device_id" in indexes
    assert "idx_devices_fcu_room_id" in indexes


def test_schema_file_contains_rooms_fcu_temp_source_and_set_range_columns():
    with closing(sqlite3.connect(":memory:")) as conn:
        with open(SCHEMA_FILE_PATH, "r", encoding="utf-8") as schema_file:
            conn.executescript(schema_file.read())
        room_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(rooms)").fetchall()
        }
        device_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(devices)").fetchall()
        }
        source_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(fcu_temp_sources)").fetchall()
        }
        range_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(fcu_set_ranges)").fetchall()
        }

    assert {"room_id", "room_name", "map_json", "fcu_device_id"} <= room_columns
    assert {
        "room_id",
        "display_name",
        "device_type",
        "device_subtype",
        "rules_enabled",
    } <= device_columns
    assert {
        "fcu_device_id",
        "source_device_id",
        "multiplier",
        "updated_at",
    } <= source_columns
    assert {
        "fcu_device_id",
        "set_range_low_c",
        "set_range_high_c",
        "updated_at",
    } <= range_columns


def test_fcu_owned_rooms_migration_bootstraps_existing_devices():
    """V9 gives every existing FCU one owned room without assigning other devices."""
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        for version in range(1, 9):
            migration = next(MIGRATION_DIR.glob(f"V{version}__*.sql"))
            conn.executescript(migration.read_text(encoding="utf-8"))

        conn.execute("INSERT INTO rooms (room_name) VALUES ('Hickory')")
        existing_room_id = conn.execute(
            "SELECT room_id FROM rooms WHERE room_name='Hickory'"
        ).fetchone()[0]
        conn.execute("INSERT INTO rooms (room_name) VALUES ('Hickory (2)')")
        conn.execute(
            """
            INSERT INTO devices (device_name, display_name, device_type, room_id)
            VALUES ('Hickory East', 'Hickory', 'FCU', ?)
            """,
            (existing_room_id,),
        )
        first_fcu_id = conn.execute(
            "SELECT device_id FROM devices WHERE device_name='Hickory East'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO devices (device_name, display_name, device_type)
            VALUES ('Hickory West', 'Hickory', 'FCU')
            """
        )
        second_fcu_id = conn.execute(
            "SELECT device_id FROM devices WHERE device_name='Hickory West'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO devices (device_name, device_type, room_id)
            VALUES ('Motion', 'SENSOR', ?)
            """,
            (existing_room_id,),
        )
        conn.execute(
            """
            INSERT INTO devices (device_name, device_type, room_id)
            VALUES ('ERV 1', 'ERV', ?)
            """,
            (existing_room_id,),
        )

        conn.executescript(
            (MIGRATION_DIR / "V9__fcu_owned_rooms.sql").read_text(encoding="utf-8")
        )

        rooms = conn.execute(
            """
            SELECT room_name, fcu_device_id
            FROM rooms
            WHERE fcu_device_id IS NOT NULL
            ORDER BY room_name
            """
        ).fetchall()
        assert [tuple(row) for row in rooms] == [
            ("Hickory", first_fcu_id),
            ("Hickory (3)", second_fcu_id),
        ]
        fcu_assignments = conn.execute(
            """
            SELECT d.device_id, d.room_id, r.fcu_device_id
            FROM devices d
            JOIN rooms r ON r.room_id = d.room_id
            WHERE d.device_type='FCU'
            ORDER BY d.device_id
            """
        ).fetchall()
        assert len(fcu_assignments) == 2
        assert tuple(fcu_assignments[0]) == (
            first_fcu_id,
            existing_room_id,
            first_fcu_id,
        )
        assert fcu_assignments[1][0] == second_fcu_id
        assert fcu_assignments[1][1] != existing_room_id
        assert fcu_assignments[1][2] == second_fcu_id
        other_assignments = conn.execute(
            "SELECT room_id FROM devices WHERE device_type IN ('SENSOR', 'ERV')"
        ).fetchall()
        assert [row[0] for row in other_assignments] == [None, None]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE devices SET room_id=? WHERE device_id=?",
                (existing_room_id, second_fcu_id),
            )


def test_alert_outbox_migration_backfills_existing_delivery_state():
    with closing(sqlite3.connect(":memory:")) as conn:
        for version in range(1, 13):
            migration = next(MIGRATION_DIR.glob(f"V{version}__*.sql"))
            conn.executescript(migration.read_text(encoding="utf-8"))
        device_id = conn.execute(
            "INSERT INTO devices (device_name) VALUES ('Airthings Dungeon')"
        ).lastrowid
        alert_id = conn.execute(
            """
            INSERT INTO alerts
                (device_id, alert_type, alert_value, start_time, end_time)
            VALUES (?, 'SensorStuck', 'ON', 1000, NULL)
            """,
            (device_id,),
        ).lastrowid
        conn.executemany(
            """
            INSERT INTO alert_events
                (alert_id, event_time, event_type, message, slack_status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                (alert_id, 1600, "triggered", "pending", "pending"),
                (alert_id, 1700, "reminder", "failed", "failed"),
                (alert_id, 1800, "resolved", "sent", "sent"),
            ),
        )

        conn.executescript(
            (MIGRATION_DIR / "V13__alert_delivery_outbox.sql").read_text(
                encoding="utf-8"
            )
        )

        events = conn.execute(
            """
            SELECT slack_status, slack_attempt_count, slack_last_attempt_time,
                   slack_next_attempt_time, slack_terminal
            FROM alert_events
            ORDER BY alert_event_id
            """
        ).fetchall()
        assert events == [
            ("pending", 0, None, 1600, 0),
            ("failed", 0, None, 1700, 0),
            ("sent", 0, None, None, 1),
        ]
        indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(alert_events)").fetchall()
        }
        assert "idx_alert_events_slack_outbox" in indexes


def test_device_subtype_migration_adds_nullable_discovery_metadata():
    """V14 adds subtype storage without guessing identity from an existing name."""
    with closing(sqlite3.connect(":memory:")) as conn:
        for version in range(1, 14):
            migration = next(MIGRATION_DIR.glob(f"V{version}__*.sql"))
            conn.executescript(migration.read_text(encoding="utf-8"))
        device_id = conn.execute(
            "INSERT INTO devices (device_name) VALUES ('Airthings Legacy')"
        ).lastrowid

        conn.executescript(
            (MIGRATION_DIR / "V14__device_subtype.sql").read_text(encoding="utf-8")
        )

        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(devices)").fetchall()
        }
        subtype = conn.execute(
            "SELECT device_subtype FROM devices WHERE device_id=?", (device_id,)
        ).fetchone()[0]
        assert "device_subtype" in columns
        assert subtype is None


def test_runtime_schema_validator_accepts_current_schema_with_flyway_history():
    with closing(sqlite3.connect(":memory:")) as conn:
        with open(SCHEMA_FILE_PATH, "r", encoding="utf-8") as schema_file:
            conn.executescript(schema_file.read())
        conn.execute(
            """
            CREATE TABLE flyway_schema_history (
                installed_rank INTEGER NOT NULL,
                version TEXT,
                description TEXT
            )
            """
        )

        db.validate_database_schema(conn)


def test_runtime_schema_validator_rejects_baseline_schema():
    with closing(sqlite3.connect(":memory:")) as conn:
        with open(BASELINE_MIGRATION_PATH, "r", encoding="utf-8") as schema_file:
            conn.executescript(schema_file.read())

        with pytest.raises(db.DatabaseSchemaMismatchError) as excinfo:
            db.validate_database_schema(conn)

    message = str(excinfo.value)
    assert "make migrate-db" in message
    assert "missing_table rooms" in message
    assert "missing_table fcu_temp_sources" in message
    assert "missing_table fcu_set_ranges" in message
    assert "devices.room_id" in message
    assert "idx_changelog_device_id_logtime" in message


def test_shared_startup_schema_check_stops_for_stale_database(
    tmp_path, monkeypatch, capsys
):
    stale_db = tmp_path / "stale.db"
    with closing(sqlite3.connect(stale_db)) as conn:
        with open(BASELINE_MIGRATION_PATH, "r", encoding="utf-8") as schema_file:
            conn.executescript(schema_file.read())

    monkeypatch.delenv("PYTEST", raising=False)
    monkeypatch.delenv(TEST_DB_NAME, raising=False)
    monkeypatch.setenv(DB_PATH, str(stale_db))

    with pytest.raises(SystemExit) as excinfo:
        db.validate_database_schema_on_startup()

    captured = capsys.readouterr()
    assert excinfo.value.code == 1
    assert captured.out == ""
    assert "Please upgrade the database" in captured.err
    assert "missing_table rooms" in captured.err
    assert "Traceback" not in captured.err


def test_shared_startup_schema_check_requires_db_path(monkeypatch, capsys):
    monkeypatch.delenv("PYTEST", raising=False)
    monkeypatch.delenv(TEST_DB_NAME, raising=False)
    monkeypatch.delenv(DB_PATH, raising=False)

    with pytest.raises(SystemExit) as excinfo:
        db.validate_database_schema_on_startup()

    captured = capsys.readouterr()
    assert excinfo.value.code == 1
    assert captured.out == ""
    assert (
        f"Missing required environment variable {DB_PATH} "
        "(path to SQLite database)." in captured.err
    )
    assert "Traceback" not in captured.err


def test_runner_uses_shared_schema_check_before_opening_database(
    tmp_path, monkeypatch, capsys
):
    stale_db = tmp_path / "stale.db"
    with closing(sqlite3.connect(stale_db)) as conn:
        with open(BASELINE_MIGRATION_PATH, "r", encoding="utf-8") as schema_file:
            conn.executescript(schema_file.read())

    monkeypatch.delenv("PYTEST", raising=False)
    monkeypatch.delenv(TEST_DB_NAME, raising=False)
    monkeypatch.setenv(DB_PATH, str(stale_db))
    monkeypatch.setattr("sys.argv", ["runner"])

    with pytest.raises(SystemExit) as excinfo:
        runner.main()

    captured = capsys.readouterr()
    assert excinfo.value.code == 1
    assert "Run `make migrate-db`" in captured.err
    assert "Traceback" not in captured.err


def test_get_db_connection_does_not_replay_schema_on_populated_database(
    tmp_path, monkeypatch
):
    stale_db = tmp_path / "stale.db"
    with closing(sqlite3.connect(stale_db)) as conn:
        with open(BASELINE_MIGRATION_PATH, "r", encoding="utf-8") as schema_file:
            conn.executescript(schema_file.read())

    monkeypatch.setenv(TEST_DB_NAME, str(stale_db))
    conn = db.get_db_connection()
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "devices" in tables
    assert "rooms" not in tables


def test_get_db_connection_initializes_empty_database(tmp_path, monkeypatch):
    empty_db = tmp_path / "empty.db"
    monkeypatch.setenv(TEST_DB_NAME, str(empty_db))

    conn = db.get_db_connection()
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert MIGRATED_APP_TABLES <= tables
