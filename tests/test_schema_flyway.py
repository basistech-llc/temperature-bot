"""Flyway schema tests."""

from contextlib import closing
import sqlite3
from pathlib import Path

from app.paths import ROOT_DIR, SCHEMA_FILE_PATH

BASELINE_APP_TABLES = {"devices", "devlog", "changelog", "aqi", "alerts"}
MIGRATED_APP_TABLES = BASELINE_APP_TABLES | {"rooms", "fcu_temp_sources"}
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
    assert "flyway_schema_history" not in tables


def test_baseline_migration_matches_deployed_changelog_device_index():
    indexes = index_names_created_by(BASELINE_MIGRATION_PATH)
    assert "idx_changelog_device_id" in indexes
    assert "idx_changelog_device_id_logtime" not in indexes


def test_schema_file_contains_migrated_changelog_device_logtime_index():
    indexes = index_names_created_by(SCHEMA_FILE_PATH)
    assert "idx_changelog_device_id_logtime" in indexes
    assert "idx_changelog_device_id" not in indexes


def test_schema_file_contains_rooms_and_fcu_temp_source_columns():
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

    assert {"room_id", "room_name", "map_json"} <= room_columns
    assert "room_id" in device_columns
    assert {
        "fcu_device_id",
        "source_device_id",
        "multiplier",
        "updated_at",
    } <= source_columns
