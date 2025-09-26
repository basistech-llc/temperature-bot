"""
Base test classes and utilities for the temperature-bot test suite.
"""
import os
import tempfile
import sqlite3
import time
import logging
import threading
import pytest

from app.main import app as flask_app

logger = logging.getLogger(__name__)

skip_on_github = pytest.mark.skipif(
    os.getenv("GITHUB_ACTIONS") == "true",
    reason="Disabled in GitHub Actions"
)


class BaseTest:
    """Base test class with common setup/teardown functionality."""

    def __init__(self):
        """Initialize test attributes."""
        self.test_db_name = None
        self.original_env = {}

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


    def create_test_database(self) -> str:
        """Create a temporary test database and return its path."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
            db_path = tf.name

        conn = sqlite3.connect(db_path)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            from .conftest import setup_test_database  # pylint: disable=import-outside-toplevel
            setup_test_database(conn)
        finally:
            conn.close()

        return db_path



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

    def __init__(self):
        """Initialize API test attributes."""
        super().__init__()
        self.client = None

    def setup_method(self):
        """Setup method for API tests."""
        super().setup_method()
        # Create a temporary directory for the database file
        from .helpers.test_utils import create_test_database_with_schema  # pylint: disable=import-outside-toplevel
        create_test_database_with_schema()

        # Override the database connection function
        flask_app.config['TESTING'] = True
        with flask_app.test_client() as test_client:
            self.client = test_client
            yield

        # Clean up the environment variables after the test
        os.environ.pop("IS_TESTING", None)
        os.environ.pop("TEST_DB_NAME", None)
