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

from conftest import client_with_db, skip_on_github, insert_temporal_test_data  # noqa: F401  # pylint: disable=unused-import
from helpers.browser_helpers import RulesTestHelper
from helpers.database_helpers import DatabaseTestHelper

from app.main import app

logger = logging.getLogger(__name__)

# Disable websockets debug
@pytest.fixture(autouse=True)
def reduce_websockets_logging():
    logging.getLogger("websockets.client").setLevel(logging.INFO)

@skip_on_github
def test_rules_disable_functionality(client_with_db: Any) -> None:  # noqa: F811 # pylint: disable=unused-argument
    """
    Test the complete rules disable/enable functionality through the browser interface.
    """

    # Create test database using new helpers
    test_db_name = os.environ['TEST_DB_PATH']

    # Create database connection and set up test data using new helpers
    db_helper = DatabaseTestHelper()
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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        helper = RulesTestHelper(page, test_db_name)

        logger.info(">> Navigate to the rules page with run_rules=0 to skip rules execution")
        page.goto("http://127.0.0.1:5100/rules?run_rules=0")
        helper.wait_for_rules_page_to_load()

        logger.info(">> Click 'disable rules button for 3600 seconds'")
        helper.click_disable_rules_button(3600)  # 1 hour = 3600 seconds

        time.sleep(0.5)         # give it time to happen
        logger.info(">> Checking to make sure rules were disabled")
        helper.verify_disable_rules_until( 3000 )

        logger.info(">> Click 'enable rules' button and verify database entry")
        helper.click_enable_rules_button()

        time.sleep(0.5)         # give it time to happen
        logger.debug(">> Check database shows rules are enabled")
        helper.check_database_rules_enabled()

        browser.close()
