"""
Base test classes and utilities for the temperature-bot test suite.
"""
import os
import tempfile
import sqlite3
import time
import logging
import threading
from typing import Any, Dict, List, Optional
from pathlib import Path
import pytest
from unittest.mock import patch

from app.main import app as flask_app
from app.paths import SCHEMA_FILE_PATH
from app import db

logger = logging.getLogger(__name__)

skip_on_github = pytest.mark.skipif(
    os.getenv("GITHUB_ACTIONS") == "true", 
    reason="Disabled in GitHub Actions"
)


class BaseTest:
    """Base test class with common setup/teardown functionality."""
    
    def setup_method(self):
        """Setup method called before each test."""
        self.test_db_name = None
        self.original_env = {}
        
    def teardown_method(self):
        """Teardown method called after each test."""
        # Clean up environment variables
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class DatabaseTest(BaseTest):
    """Database-specific test utilities."""
    
    def setup_test_database(self, conn: sqlite3.Connection) -> None:
        """Set up the database schema on a given connection."""
        logging.debug("*** setup_test_database")
        cursor = conn.cursor()
        try:
            if not os.path.exists(SCHEMA_FILE_PATH):
                logging.error("Schema file not found at %s. Please ensure it exists.", SCHEMA_FILE_PATH)
                raise FileNotFoundError(f"Schema file not found at {SCHEMA_FILE_PATH}")

            with open(SCHEMA_FILE_PATH, 'r') as f:
                schema_sql = f.read()

            cursor.executescript(schema_sql)
            conn.commit()
            cursor.execute("INSERT INTO aqi VALUES (?,?)", (int(time.time()), 45))  # insert AQI of 45
            logging.debug("*** sending schema")
            logging.info("Test database schema set up successfully from %s.", SCHEMA_FILE_PATH)
        except sqlite3.Error as e:
            logging.exception("Test database error during schema setup: %s", e)
            conn.rollback()
            raise

    def create_test_database(self) -> str:
        """Create a temporary test database and return its path."""
        tf = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tf.close()
        
        conn = sqlite3.connect(tf.name)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        self.setup_test_database(conn)
        conn.close()
        
        return tf.name

    def insert_temporal_test_data(self, conn: sqlite3.Connection, device_name: str = "Test Device") -> tuple[int, Dict[str, int]]:
        """
        Creates test data with records at different time intervals:
        - 1 hour ago
        - 26 hours ago  
        - 200 hours ago
        - 2000 hours ago

        Returns the device_id and a dict with the expected record counts for different time ranges.
        """
        current_time = int(time.time())

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


class BrowserTest(BaseTest):
    """Browser test utilities with common helpers."""
    
    def __init__(self):
        super().__init__()
        self.server_thread = None
        self.server_port = None
        
    def start_flask_server(self, port: int = 5000) -> None:
        """Start Flask server in a separate thread."""
        def run_app():
            flask_app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)
            
        self.server_thread = threading.Thread(target=run_app, daemon=True)
        self.server_thread.start()
        self.server_port = port
        
        # Give the server time to start
        time.sleep(3)
        
    def stop_flask_server(self) -> None:
        """Stop the Flask server thread."""
        if self.server_thread:
            # The thread will be terminated when the process ends
            self.server_thread = None
            self.server_port = None

    def get_server_url(self) -> str:
        """Get the server URL."""
        if self.server_port is None:
            raise RuntimeError("Server not started. Call start_flask_server() first.")
        return f"http://127.0.0.1:{self.server_port}"


class APITest(BaseTest):
    """API endpoint test utilities."""
    
    def setup_method(self):
        """Setup method for API tests."""
        super().setup_method()
        # Create a temporary directory for the database file
        with tempfile.NamedTemporaryFile(suffix='.db') as tf:
            logging.info("Created temporary database file for test: %s", tf.name)

            # Temporarily set an environment variable to tell lifespan we are testing
            os.environ['IS_TESTING'] = 'True'
            # IMPORTANT: Also set TEST_DB_NAME environment variable for db.py's get_db_connection
            # to ensure it connects to this temporary file.
            os.environ['TEST_DB_NAME'] = tf.name

            # Set up the database schema in the temporary file
            conn = sqlite3.connect(tf.name)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            
            # Setup database schema
            db_test = DatabaseTest()
            db_test.setup_test_database(conn)
            conn.close()

            # Override the database connection function
            flask_app.config['TESTING'] = True
            with flask_app.test_client() as test_client:
                self.client = test_client
                yield

            # Clean up the environment variables after the test
            os.environ.pop("IS_TESTING", None)
            os.environ.pop("TEST_DB_NAME", None)


class TestDataFactory:
    """Factory for creating consistent test data."""
    
    @staticmethod
    def create_broadway_south_device(conn: sqlite3.Connection, ae200_device_id: int = 10) -> int:
        """Create Broadway South device for testing."""
        device_id = db.get_or_create_device_id(conn, "Broadway South")
        c = conn.cursor()
        c.execute("UPDATE devices set ae200_device_id=? where device_id=?", (ae200_device_id, device_id))
        conn.commit()
        return device_id
    
    @staticmethod
    def create_device_with_status(conn: sqlite3.Connection, device_name: str, 
                                status_dict: Dict[str, Any], logtime: Optional[int] = None) -> int:
        """Create a device with initial status data."""
        if logtime is None:
            logtime = int(time.time())
            
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
    
    @staticmethod
    def create_mock_weather_data(temperature: int = 32) -> Dict[str, Any]:
        """Create mock weather data for testing."""
        return {
            "current": {"temperature": temperature, "conditions": "Sunny"},
            "forecast": []
        }
    
    @staticmethod
    def create_mock_aqi_data() -> int:
        """Create mock AQI data for testing."""
        return 45


class MockHelper:
    """Helper class for setting up common mocks."""
    
    @staticmethod
    def setup_weather_mocks(mock_get_airquality, mock_get_weather_data, 
                           aqi_value: int = 45, temperature: int = 32):
        """Setup common weather and AQI mocks."""
        mock_get_airquality.return_value = aqi_value
        mock_get_weather_data.return_value = TestDataFactory.create_mock_weather_data(temperature)
    
    @staticmethod
    def setup_ae200_mocks(mock_get_devices, mock_get_device_info, 
                          test_data_dir: str, device_id: int = 10):
        """Setup common AE200 device mocks."""
        import json
        from pathlib import Path
        
        # Load test data
        with open(Path(test_data_dir) / 'get_devices.json') as f:
            mock_get_devices.return_value = json.load(f)
        
        with open(Path(test_data_dir) / f'get_device_{device_id}.json') as f:
            mock_get_device_info.return_value = json.load(f)
