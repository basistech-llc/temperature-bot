"""
Test the rules disable functionality through the browser interface.
"""

import os
import time
import logging
import threading
from typing import Any

import pytest
from playwright.sync_api import sync_playwright

from conftest import client, skip_on_github, insert_temporal_test_data  # noqa: F401  # pylint: disable=unused-import
from helpers.browser_helpers import RulesTestHelper
from helpers.database_helpers import DatabaseTestHelper

from app.main import app


logger = logging.getLogger(__name__)


# Disable websockets debug
@pytest.fixture(autouse=True)
def reduce_websockets_logging():
    logging.getLogger("websockets.client").setLevel(logging.INFO)


def test_rules_disable_functionality(client: Any) -> None:  # noqa: F811 # pylint: disable=unused-argument
    """
    Test the complete rules disable/enable functionality through the browser interface.
    """

    # Create test database using new helpers
    test_db_name = os.environ['TEST_DB_NAME']

    # Create database connection and set up test data using new helpers
    db_helper = DatabaseTestHelper(test_db_name)
    with db_helper.get_connection() as conn:
        insert_temporal_test_data(conn)

    def run_app():
        """Run the Flask app in a separate thread"""
        app.run(host="127.0.0.1", port=5100, debug=False, use_reloader=False)

    # Start the app in a separate thread
    server_thread = threading.Thread(target=run_app, daemon=True) # server for test_rules_disable.py
    server_thread.start()

    # Give the app time to start
    time.sleep(3)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            helper = RulesTestHelper(page, test_db_name)

            # Navigate to the rules page with run_rules=0 to skip rules execution
            page.goto("http://127.0.0.1:5100/rules?run_rules=0")
            helper.wait_for_rules_page_to_load()

            # Test 1: Click "enable rules" button and verify database entry
            logger.info("Testing enable rules button...")
            helper.click_enable_rules_button()

            # Wait for page refresh and verify rules are enabled
            helper.verify_rules_enabled()

            # Check database shows rules are enabled
            helper.check_database_rules_enabled()

            # Test 2: Click "disable for 1 hour" button and verify database entry
            logger.info("Testing disable rules for 1 hour...")
            helper.click_disable_rules_button(3600)  # 1 hour = 3600 seconds

            # Wait for page refresh and verify rules are disabled
            # Should be disabled for at least 50 minutes
            #time.sleep(1)       # this shouldn't be needed.
            helper.verify_rules_disabled_until( 50 )

            browser.close()

    except Exception as e:
        logger.error("Browser page error: %s",e)
        raise
    finally:
        # Clean up
        pass
