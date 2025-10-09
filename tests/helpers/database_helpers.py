"""
Database test helpers and utilities.
"""
import os
import sqlite3
import logging
from typing import Optional
from .test_utils import verify_changelog_entry, verify_devlog_entry

logger = logging.getLogger(__name__)


class DatabaseTestHelper:
    """Helper class for database testing operations."""

    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect( os.environ['TEST_DB_NAME'] )
        conn.row_factory = sqlite3.Row
        return conn

    def verify_changelog_entry(self, device_id: int, expected_value: str, expected_agent: str = "web"):
        """Verify the most recent changelog entry for a device."""
        with self.get_connection() as conn:
            verify_changelog_entry(conn, device_id, expected_value, expected_agent)

    def verify_devlog_entry(self, device_id: int, expected_fan_speed: int):
        """Verify the most recent devlog entry has the expected fan speed."""
        with self.get_connection() as conn:
            verify_devlog_entry(conn, device_id, expected_fan_speed)

    def get_device_count(self) -> int:
        """Get the total number of devices in the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM devices")
            return cursor.fetchone()[0]

    def get_devlog_count(self, device_id: Optional[int] = None) -> int:
        """Get the total number of devlog entries, optionally filtered by device_id."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if device_id is not None:
                cursor.execute("SELECT COUNT(*) FROM devlog WHERE device_id = ?", (device_id,))
            else:
                cursor.execute("SELECT COUNT(*) FROM devlog")
            return cursor.fetchone()[0]
