"""
Browser test helpers for Playwright-based tests.
"""
import logging
import time
import sqlite3
from playwright.sync_api import Page, expect
from app import db
from tests.helpers.test_utils import verify_changelog_entry, verify_devlog_entry

logger = logging.getLogger(__name__)


class BrowserTestHelper:
    """Helper class for browser testing operations"""

    def __init__(self, page: Page, test_db_name: str):
        self.page = page
        self.test_db_name = test_db_name

    def wait_for_grid_to_load(self):
        """Wait for the main grid to load and be visible"""
        # Wait for the table to be created
        self.page.wait_for_selector('table.pure-table', timeout=10000)
        # Wait for at least one device row to be present
        self.page.wait_for_selector('tr:has(td)', timeout=10000)

    def find_broadway_south_row(self):
        """Find the Broadway South row in the table"""
        # Look for a row containing "Broadway South"
        return self.page.locator('tr:has-text("Broadway South")')

    def get_fan_speed_radio(self, speed: int):
        """Get the radio button for a specific fan speed for Broadway South"""
        # Find the Broadway South row and get the radio button for the specified speed
        row = self.find_broadway_south_row()
        logger.debug("row=%s", row)
        assert row is not None
        # The radio button ID format is radio-{device_id}-{speed}
        # We need to find the device_id first
        device_id = self.get_broadway_south_device_id()
        return self.page.locator(f'#radio-{device_id}-{speed}')

    def get_broadway_south_device_id(self) -> int:
        """Get the device ID for Broadway South from the database"""

        with sqlite3.connect(self.test_db_name) as conn:
            conn.row_factory = sqlite3.Row
            device_id = db.get_or_create_device_id(conn, "Broadway South")
            return device_id

    def click_fan_speed(self, speed: int):
        """Click on a fan speed radio button for Broadway South"""
        radio = self.get_fan_speed_radio(speed)
        radio.click()

    def verify_radio_selected(self, speed: int):
        """Verify that the specified fan speed radio button is selected"""
        radio = self.get_fan_speed_radio(speed)
        expect(radio).to_be_checked()

    def verify_radio_not_selected(self, speed: int):
        """Verify that the specified fan speed radio button is not selected"""
        radio = self.get_fan_speed_radio(speed)
        expect(radio).not_to_be_checked()

    def verify_database_speed(self, expected_fan_speed: int):
        """Verify that the database has been updated with the expected speed"""

        device_id = self.get_broadway_south_device_id()

        with sqlite3.connect(self.test_db_name) as conn:
            conn.row_factory = sqlite3.Row
            verify_changelog_entry(conn, device_id, str(expected_fan_speed), 'web')
            verify_devlog_entry(conn, device_id, expected_fan_speed)


class TemperatureTestHelper:
    """Helper class for temperature display testing operations"""

    def __init__(self, page: Page, test_db_name: str):
        self.page = page
        self.test_db_name = test_db_name

    def wait_for_chart_to_load(self):
        """Wait for the chart page to load and be visible"""
        # Wait for the main chart container
        self.page.wait_for_selector('#main', timeout=10000)
        # Wait for the record count to appear
        self.page.wait_for_selector('#record-count', timeout=10000)

    def get_record_count(self) -> int:
        """Get the current record count from the page"""
        record_count_element = self.page.locator('#record-count')
        text = record_count_element.text_content()
        # Extract number from "Records loaded: X"
        count = int(text.split(': ')[1])
        return count

    def click_temporal_button(self, button_name: str):
        """Click a temporal button (day, week, month)"""
        button_map = {
            'day': '#dayBtn',
            'week': '#weekBtn',
            'month': '#monthBtn'
        }
        button_selector = button_map.get(button_name)
        if not button_selector:
            raise ValueError(f"Unknown button: {button_name}")

        self.page.click(button_selector)
        # Wait for the record count to update
        time.sleep(1)

    def verify_record_count(self, expected_count: int):
        """Verify that the record count matches the expected value"""
        actual_count = self.get_record_count()
        assert actual_count == expected_count, \
            f"Expected {expected_count} records, got {actual_count}"


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
        assert button is not None
        button.click()

    def verify_disable_rules_until(self, expected_seconds: int) -> None:
        """Verify that rules all rules are disabled for at least the expected number of seconds"""

        # Wait for page to refresh and check for disabled rules text
        # the rules.html page no longer does this.
        #try:
        #    # Wait for page to refresh and check for disabled rules text
        #    self.page.wait_for_selector('h2:has-text("Rules disabled until")', timeout=10000)
        #except playwright.sync_api.TimeoutError as e:
        #    # Dump full HTML for debugging
        #    html = self.page.content()
        #    with open("debug_dump.html", "w", encoding="utf-8") as f:
        #        f.write(html)
        #    raise AssertionError("Expected text 'Rules disabled until' not found. Page dumped to debug_dump.html") from e

        # Check the database to verify rules are actually disabled
        disabled_until_atleast = int(time.time()) + expected_seconds
        with sqlite3.connect(self.test_db_name) as conn:
            conn.row_factory = sqlite3.Row
            drr = db.disable_rules_report(conn)
            logger.info("drr=%s", drr)

            # Assert that every device has a disabled rule
            for (k,v) in drr.items():
                logger.info("verify_disable_rules_until "
                            "k=%s v=%s disabled_until_atleast=%s",k,dict(v),disabled_until_atleast)
                assert v['disabled_until'] > disabled_until_atleast

    def check_database_rules_enabled(self) -> None:
        """Check that the database shows rules are enabled"""

        with sqlite3.connect(self.test_db_name) as conn:
            conn.row_factory = sqlite3.Row
            drr = db.disable_rules_report(conn)
            logger.info("drr=%s", drr)

            # Assert that every device has a disabled rule
            for (device_id,row) in drr.items():
                logger.info("check_database_rules_enabled: device_id=%s row=%s",device_id,dict(row))
                assert row['disabled_until'] == 0
