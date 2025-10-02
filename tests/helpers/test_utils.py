"""
Shared test utilities to avoid code duplication.
"""
import os
import tempfile
import sqlite3
import logging
import json
import time
from app import ae200
from app import db
from app.paths import SCHEMA_FILE_PATH

def create_test_database_with_schema():
    """Create a temporary test database with schema and return the file path."""
    with  tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
        db_path = tf.name

    logging.info("Created temporary database file for test: %s", db_path)
    os.environ['IS_TESTING'] = 'True'
    os.environ['TEST_DB_PATH'] = db_path
    conn = db.get_db_connection(schema_file = SCHEMA_FILE_PATH, testing=True)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO aqi (logtime,aqi) VALUES (?,?)", (int(time.time()), 45))  # insert AQI of 45
    conn.commit()
    conn.close()
    return db_path

def cleanup_test_database_with_schema():
    os.unlink(os.environ['TEST_DB_PATH'])
    os.environ.pop("IS_TESTING", None)
    os.environ.pop("TEST_DB_PATH", None)

def verify_changelog_entry(conn: sqlite3.Connection, device_id: int, expected_value: str, expected_agent: str = "web"):
    """Verify the most recent changelog entry for a device."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT new_value, agent FROM changelog
        WHERE device_id = ?
        ORDER BY changelog_id DESC
        LIMIT 1
    """, (device_id,))
    changelog_entry = cursor.fetchone()

    assert changelog_entry is not None, "No changelog entry found"
    assert changelog_entry['new_value'] == expected_value, \
        f"Expected value {expected_value}, got {changelog_entry['new_value']}"
    assert changelog_entry['agent'] == expected_agent, \
        f"Expected agent '{expected_agent}', got {changelog_entry['agent']}"


def verify_devlog_entry(conn: sqlite3.Connection, device_id: int, expected_fan_speed: int):
    """Verify the most recent devlog entry has the expected fan speed."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT status_json FROM devlog
        WHERE device_id = ?
        ORDER BY logtime DESC
        LIMIT 1
    """, (device_id,))
    devlog_entry = cursor.fetchone()

    assert devlog_entry is not None, "No devlog entry found"
    status_data = json.loads(devlog_entry['status_json'])
    extracted_status = ae200.extract_drive_and_fan_speed(status_data)
    assert extracted_status['fan_speed'] == expected_fan_speed, \
        f"Expected fan_speed {expected_fan_speed}, got {extracted_status['fan_speed']}"
