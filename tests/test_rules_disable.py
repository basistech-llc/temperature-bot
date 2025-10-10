"""
Test the rules disable functionality through the browser interface.
"""

import os
import time
import logging
import threading

from playwright.sync_api import sync_playwright

from conftest import skip_on_github  # noqa: F401  # pylint: disable=unused-import
from helpers.browser_helpers import RulesTestHelper

from app.main import app


logger = logging.getLogger(__name__)

def test_rules_disable_functionality(test_database_conn_with_test_data) -> None:   # noqa: F811 # pylint: disable=unused-argument
    """
    Test the complete rules disable/enable functionality through the browser interface.
    """

    # Create database connection and set up test data using new helpers

    def run_app():
        """Run the Flask app in a separate thread"""
        app.run(host="127.0.0.1", port=5100, debug=False, use_reloader=False)

    # Start the app in a separate thread
    server_thread = threading.Thread(target=run_app, daemon=True) # server for test_rules_disable.py
    server_thread.start()

    # Give the app time to start
    time.sleep(3)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        helper = RulesTestHelper(page, os.environ['TEST_DB_NAME'])

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
        time.sleep(0.5)
        helper.verify_rules_disabled_until( 50 )
        browser.close()
