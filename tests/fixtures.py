#!/usr/bin/env python3
"""
Simple test to check if Flask routes are working
"""
import os
import tempfile
import sqlite3
import logging
import pytest
from app.main import app as flask_app
from app.paths import SCHEMA_FILE_PATH

skip_on_github = pytest.mark.skipif(os.getenv("GITHUB_ACTIONS") == "true", reason="Disabled in GitHub Actions")

# Override the setup_database function for testing
def setup_test_database(conn):
    """
    Sets up the database schema on a given connection by reading from schema.sql.
    """
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
        logging.debug("*** sending schema")
        logging.info("Test database schema set up successfully from %s.", SCHEMA_FILE_PATH)
    except sqlite3.Error as e:
        logging.exception("Test database error during schema setup: %s", e)
        conn.rollback()

@pytest.fixture
def client():
    """Provides a Flask test client with overridden database connection using a temporary file DB."""
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
        setup_test_database(conn)
        conn.close()

        # Override the database connection function
        flask_app.config['TESTING'] = True
        with flask_app.test_client() as test_client:
            yield test_client

        # Clean up the environment variables after the test
        os.environ.pop("IS_TESTING", None)
        os.environ.pop("TEST_DB_NAME", None)
