"""Flyway schema tests."""

import sqlite3
from pathlib import Path

from app.paths import ROOT_DIR, SCHEMA_FILE_PATH

APP_TABLES = {"devices", "devlog", "changelog", "aqi", "alerts"}
BASELINE_MIGRATION_PATH = (
    Path(ROOT_DIR) / "etc" / "flyway" / "sql" / "V1__baseline_schema.sql"
)


def table_names_created_by(sql_path):
    conn = sqlite3.connect(":memory:")
    with open(sql_path, "r", encoding="utf-8") as schema_file:
        conn.executescript(schema_file.read())
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def index_names_created_by(sql_path):
    conn = sqlite3.connect(":memory:")
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
    assert APP_TABLES <= tables
    assert "flyway_schema_history" not in tables


def test_baseline_migration_does_not_create_flyway_history_table():
    tables = table_names_created_by(BASELINE_MIGRATION_PATH)
    assert APP_TABLES <= tables
    assert "flyway_schema_history" not in tables


def test_baseline_migration_matches_deployed_changelog_device_index():
    indexes = index_names_created_by(BASELINE_MIGRATION_PATH)
    assert "idx_changelog_device_id" in indexes
    assert "idx_changelog_device_id_logtime" not in indexes


def test_schema_file_contains_migrated_changelog_device_logtime_index():
    indexes = index_names_created_by(SCHEMA_FILE_PATH)
    assert "idx_changelog_device_id_logtime" in indexes
    assert "idx_changelog_device_id" not in indexes
