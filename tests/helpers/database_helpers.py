"""
Database test helpers and utilities.
"""
import sqlite3
import time
import logging
from typing import Dict, Any, Optional
from app import db

logger = logging.getLogger(__name__)


class DatabaseTestHelper:
    """Helper class for database testing operations."""
    
    def __init__(self, test_db_name: str):
        self.test_db_name = test_db_name
    
    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.test_db_name)
        conn.row_factory = sqlite3.Row
        return conn
    
    def create_broadway_south_device(self, ae200_device_id: int = 10) -> int:
        """Create Broadway South device for testing."""
        with self.get_connection() as conn:
            device_id = db.get_or_create_device_id(conn, "Broadway South")
            c = conn.cursor()
            c.execute("UPDATE devices set ae200_device_id=? where device_id=?", (ae200_device_id, device_id))
            conn.commit()
            return device_id
    
    def create_device_with_initial_status(self, device_name: str, 
                                       status_dict: Dict[str, Any], 
                                       logtime: Optional[int] = None) -> int:
        """Create a device with initial status data."""
        if logtime is None:
            logtime = int(time.time())
            
        with self.get_connection() as conn:
            device_id = db.get_or_create_device_id(conn, device_name)
            db.insert_devlog_entry(
                conn,
                device_id=device_id,
                temp=float(status_dict.get('InletTemp', 24.0)),
                statusdict=status_dict,
                logtime=logtime,
                force=True
            )
            return device_id
    
    def insert_temporal_test_data(self, device_name: str = "Temporal Test Device") -> tuple[int, Dict[str, int]]:
        """
        Creates test data with records at different time intervals:
        - 1 hour ago
        - 26 hours ago  
        - 200 hours ago
        - 2000 hours ago

        Returns the device_id and a dict with the expected record counts for different time ranges.
        """
        current_time = int(time.time())

        with self.get_connection() as conn:
            # Create device
            cursor = conn.cursor()
            cursor.execute("INSERT INTO devices (device_name) VALUES (?)", (device_name,))
            device_id = cursor.lastrowid

            # Define time intervals in seconds
            intervals = {
                "1_hour": 1 * 60 * 60,
                "26_hours": 26 * 60 * 60,
                "200_hours": 200 * 60 * 60,
                "2000_hours": 2000 * 60 * 60
            }

            # Add records at each interval. Initial speed is always LOW.
            for interval_name, seconds in intervals.items():  # pylint: disable=unused-variable
                record_time = current_time - seconds
                cursor.execute("""
                    INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (device_id, record_time, 60, 240, '{"Drive": "ON", "FanSpeed": "LOW", "InletTemp": "24.0"}'))

            conn.commit()

            # Calculate expected record counts for different time ranges
            expected_counts = {
                "day": 1,    # Only 1 hour ago
                "week": 2,   # 1 hour + 26 hours ago
                "month": 3,  # 1 hour + 26 hours + 200 hours ago
                "all": 4     # All records
            }

            return device_id, expected_counts
    
    def verify_changelog_entry(self, device_id: int, expected_value: str, expected_agent: str = "web"):
        """Verify the most recent changelog entry for a device."""
        with self.get_connection() as conn:
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
    
    def verify_devlog_entry(self, device_id: int, expected_fan_speed: int):
        """Verify the most recent devlog entry has the expected fan speed."""
        import json
        from app import ae200
        
        with self.get_connection() as conn:
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
