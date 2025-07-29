"""
Test the rules disable functionality through the browser interface.
"""

import os
import sqlite3
import time
import logging
import threading
from typing import Any

import pytest
from playwright.sync_api import sync_playwright, Page

from fixtures import client, skip_on_github, insert_temporal_test_data  # noqa: F401  # pylint: disable=unused-import
from app import rules_engine

from app.main import app
from playwright.sync_api import TimeoutError


logger = logging.getLogger(__name__)


# Disable websockets debug
@pytest.fixture(autouse=True)
def reduce_websockets_logging():
    logging.getLogger("websockets.client").setLevel(logging.INFO)


class RulesTestHelper:
    """Helper class for rules testing operations"""

    def __init__(self, page: Page, test_db_name: str) -> None:
        self.page = page
        self.test_db_name = test_db_name

    def wait_for_rules_page_to_load(self) -> None:
        """Wait for the rules page to load and be visible"""
        # Wait for the devices table to be created
        self.page.wait_for_selector("table", timeout=10000)
        # Wait for the rules content to be present
        self.page.wait_for_selector("pre", timeout=10000)

    def click_enable_rules_button(self) -> None:
        """Click the enable rules button"""
        button = self.page.locator('button[x-seconds="0"]')
        button.click()

    def click_disable_rules_button(self, seconds: int) -> None:
        """Click a disable rules button with the specified seconds"""
        button = self.page.locator(f'button[x-seconds="{seconds}"]')
        button.click()

    def verify_rules_enabled(self) -> None:
        """Verify that rules are enabled by checking the page content"""
        # Wait for page to refresh and check for "Rules enabled" text
        self.page.wait_for_selector('h2:has-text("Rules enabled")', timeout=10000)

    def verify_rules_disabled_until(self, expected_minutes: int) -> None:
        """Verify that rules are disabled for at least the expected number of minutes"""
        # Wait for page to refresh and check for disabled rules text
        try:
            # Wait for page to refresh and check for disabled rules text
            self.page.wait_for_selector('h2:has-text("Rules disabled until")', timeout=10000)
        except TimeoutError:
            # Dump full HTML for debugging
            html = self.page.content()
            with open("debug_dump.html", "w", encoding="utf-8") as f:
                f.write(html)
            raise AssertionError("Expected text 'Rules disabled until' not found. Page dumped to debug_dump.html")

        # Check the database to verify rules are actually disabled
        with sqlite3.connect(self.test_db_name) as conn:
            conn.row_factory = sqlite3.Row
            disabled_until = rules_engine.rules_disabled_until(conn)
            logger.info("disabled_until=%s",disabled_until)
            assert disabled_until != 0

            current_time = time.time()
            min_expected_time = current_time + (expected_minutes * 60)

            logger.info("Current time: %s", current_time)
            logger.info("Disabled until: %s", disabled_until)
            logger.info("Min expected time: %s", min_expected_time)

            assert disabled_until >= min_expected_time, f"Rules should be disabled until at least {min_expected_time}, but got {disabled_until}"


    def check_database_rules_enabled(self) -> None:
        """Check that the database shows rules are enabled"""
        with sqlite3.connect(self.test_db_name) as conn:
            conn.row_factory = sqlite3.Row
            disabled_until = rules_engine.rules_disabled_until(conn)
            assert disabled_until == 0, "Rules should be enabled (disabled_until=0), but got {disabled_until}"


def test_rules_disable_functionality(client: Any) -> None:  # noqa: F811 # pylint: disable=unused-argument
    """
    Test the complete rules disable/enable functionality through the browser interface.
    """

    # Create test database
    test_db_name = os.environ['TEST_DB_NAME']

    # Create database connection and set up test data
    with sqlite3.connect(test_db_name) as conn:
        conn.row_factory = sqlite3.Row
        insert_temporal_test_data(conn)

    def run_app():
        """Run the Flask app in a separate thread"""
        app.run(host="127.0.0.1", port=5100, debug=False, use_reloader=False)

    # Start the app in a separate thread
    server_thread = threading.Thread(target=run_app, daemon=True)
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
