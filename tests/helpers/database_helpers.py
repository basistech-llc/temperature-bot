"""
Database test helpers and utilities.
"""
import os
import sqlite3
import logging
from typing import Optional
import pytest
from .test_utils import verify_changelog_entry, verify_devlog_entry

logger = logging.getLogger(__name__)


@pytest.fixture
def dbc():
    """simple database connection fixture for this database_helpers..."""
    with sqlite3.connect( os.environ['TEST_DB_NAME'] ) as conn:
        conn.row_factory = sqlite3.Row
        yield conn

class DatabaseTestHelper:
    """Helper class for database testing operations."""

    def verify_changelog_entry(self, dbc, device_id: int, expected_value: str, expected_agent: str = "web"):
        """Verify the most recent changelog entry for a device."""
        verify_changelog_entry(dbc, device_id, expected_value, expected_agent)

    def verify_devlog_entry(self, dbc, device_id: int, expected_fan_speed: int):
        """Verify the most recent devlog entry has the expected fan speed."""
        verify_devlog_entry(dbc, device_id, expected_fan_speed)

    def get_device_count(self, dbc) -> int:
        """Get the total number of devices in the database."""
        cursor = dbc.cursor()
        cursor.execute("SELECT COUNT(*) FROM devices")
        return cursor.fetchone()[0]

    def get_devlog_count(self, dbc, device_id: Optional[int] = None) -> int:
        """Get the total number of devlog entries, optionally filtered by device_id."""
        cursor = dbc.cursor()
        if device_id is not None:
            cursor.execute("SELECT COUNT(*) FROM devlog WHERE device_id = ?", (device_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM devlog")
        return cursor.fetchone()[0]
