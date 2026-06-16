"""Flyway schema tests."""

from contextlib import closing
import sqlite3
from pathlib import Path

import pytest

from app import db
from app import main
from app.constants import DB_PATH, TEST_DB_NAME
from app.paths import ROOT_DIR, SCHEMA_FILE_PATH

BASELINE_APP_TABLES = {"devices", "devlog", "changelog", "aqi", "alerts"}
MIGRATED_APP_TABLES = BASELINE_APP_TABLES | {
    "rooms",
    "fcu_temp_sources",
    "fcu_set_ranges",
}
BASELINE_MIGRATION_PATH = (
    Path(ROOT_DIR) / "etc" / "flyway" / "sql" / "V1__baseline_schema.sql"
)


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

    assert {"room_id", "room_name", "map_json"} <= room_columns
    assert "room_id" in device_columns
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


def test_flask_startup_schema_check_stops_for_stale_database(tmp_path, monkeypatch):
    stale_db = tmp_path / "stale.db"
    with closing(sqlite3.connect(stale_db)) as conn:
        with open(BASELINE_MIGRATION_PATH, "r", encoding="utf-8") as schema_file:
            conn.executescript(schema_file.read())

    monkeypatch.delenv("PYTEST", raising=False)
    monkeypatch.delenv(TEST_DB_NAME, raising=False)
    monkeypatch.setenv(DB_PATH, str(stale_db))

    with pytest.raises(db.DatabaseSchemaMismatchError) as excinfo:
        main.validate_database_schema_on_startup()

    assert "Please upgrade the database" in str(excinfo.value)
