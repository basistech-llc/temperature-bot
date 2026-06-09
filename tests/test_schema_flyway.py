"""Flyway schema tests."""

import sqlite3

from app.paths import SCHEMA_FILE_PATH


def test_schema_includes_flyway_history_table():
    conn = sqlite3.connect(":memory:")
    with open(SCHEMA_FILE_PATH, "r", encoding="utf-8") as schema_file:
        conn.executescript(schema_file.read())
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='flyway_schema_history'"
    ).fetchone()
    assert row is not None
