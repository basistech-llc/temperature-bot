"""
Browser test helpers for Playwright-based tests.
"""

import logging
import time
import sqlite3
import json
from playwright.sync_api import Page, expect
import playwright.sync_api
from app import db, rules_engine
from app import ae200

logger = logging.getLogger(__name__)


def verify_changelog_entry(
    conn: sqlite3.Connection,
    device_id: int,
    expected_value: str,
    expected_agent: str = "web",
):
    """Verify the most recent changelog entry for a device."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT new_value, agent FROM changelog
        WHERE device_id = ?
        ORDER BY changelog_id DESC
        LIMIT 1
    """,
        (device_id,),
    )
    changelog_entry = cursor.fetchone()

    assert changelog_entry is not None, "No changelog entry found"
    assert changelog_entry["new_value"] == expected_value, (
        f"Expected value {expected_value}, got {changelog_entry['new_value']}"
    )
    assert changelog_entry["agent"] == expected_agent, (
        f"Expected agent '{expected_agent}', got {changelog_entry['agent']}"
    )


def verify_devlog_entry(
    conn: sqlite3.Connection, device_id: int, expected_fan_speed: int
):
    """Verify the most recent devlog entry has the expected fan speed."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT status_json FROM devlog
        WHERE device_id = ?
        ORDER BY logtime DESC
        LIMIT 1
    """,
        (device_id,),
    )
    devlog_entry = cursor.fetchone()

    assert devlog_entry is not None, "No devlog entry found"
    status_data = json.loads(devlog_entry["status_json"])
    extracted_status = ae200.extract_drive_and_fan_speed(status_data)
    assert extracted_status["fan_speed"] == expected_fan_speed, (
        f"Expected fan_speed {expected_fan_speed}, got {extracted_status['fan_speed']}"
    )


class BrowserTestHelper:
    """Helper class for browser testing operations"""

    def __init__(self, page: Page, test_db_name: str):
        self.page = page
        self.test_db_name = test_db_name

    def wait_for_grid_to_load(self):
        """Wait for the main grid to load and be visible"""
        # Wait for the table to be created
        self.page.wait_for_selector("table.pure-table", timeout=10000)
        # Wait for at least one device row to be present
        self.page.wait_for_selector("tr:has(td)", timeout=10000)

    def find_broadway_south_row(self, device_name: str = "Broadway Test"):
        """Find the device row in the table (default Broadway Test)."""
        return self.page.locator("tr:has-text(\"" + device_name + "\")")

    def get_fan_speed_radio(self, speed: int, device_name: str = "Broadway Test"):
        """Get the radio button for a specific fan speed for the given device."""
        device_id = self.get_broadway_south_device_id(device_name)
        return self.page.locator(f"#radio-{device_id}-{speed}")

    def get_broadway_south_device_id(self, device_name: str = "Broadway Test") -> int:
        """Get the device ID for the given name from the database (default Broadway Test)."""
        conn = sqlite3.connect(self.test_db_name)
        conn.row_factory = sqlite3.Row
        device_id = db.get_or_create_device_id(conn, device_name)
        conn.close()
        return device_id

    def click_fan_speed(self, speed: int, device_name: str = "Broadway Test"):
        """Click on a fan speed radio button for the given device."""
        radio = self.get_fan_speed_radio(speed, device_name)
        radio.click()

    def verify_radio_selected(self, speed: int, device_name: str = "Broadway Test"):
        """Verify that the specified fan speed radio button is selected."""
        radio = self.get_fan_speed_radio(speed, device_name)
        expect(radio).to_be_checked()

    def verify_radio_not_selected(self, speed: int, device_name: str = "Broadway Test"):
        """Verify that the specified fan speed radio button is not selected."""
        radio = self.get_fan_speed_radio(speed, device_name)
        expect(radio).not_to_be_checked()

    def verify_database_speed(self, expected_fan_speed: int):
        """Verify that the database has been updated with the expected speed"""

        device_id = self.get_broadway_south_device_id()

        conn = sqlite3.connect(self.test_db_name)
        conn.row_factory = sqlite3.Row
        verify_changelog_entry(conn, device_id, str(expected_fan_speed), "web")
        verify_devlog_entry(conn, device_id, expected_fan_speed)
        conn.close()


class TemperatureTestHelper:
    """Helper class for temperature display testing operations"""

    def __init__(self, page: Page, test_db_name: str):
        self.page = page
        self.test_db_name = test_db_name

    def wait_for_chart_to_load(self):
        """Wait for the chart page to load and be visible"""
        # Wait for the chart controls and record count (chart.html has #controls, #temp-chart, #record-count)
        self.page.wait_for_selector("#controls", timeout=10000)
        self.page.wait_for_selector("#record-count", timeout=10000)

    def get_record_count(self) -> int:
        """Get the current record count from the page"""
        record_count_element = self.page.locator("#record-count")
        text = record_count_element.text_content()
        # Extract number from "Total temperature datapoints: X"
        count = int(text.split(": ")[1].strip())
        return count

    def click_temporal_button(self, button_name: str):
        """Click a temporal button (day, week, month, all)"""
        button_map = {
            "day": "#dayBtn",
            "week": "#weekBtn",
            "month": "#monthBtn",
            "all": "#allBtn",
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
        assert actual_count == expected_count, (
            f"Expected {expected_count} records, got {actual_count}"
        )


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
            self.page.wait_for_selector(
                'h2:has-text("Rules disabled until")', timeout=10000
            )
        except playwright.sync_api.TimeoutError as e:
            # Dump full HTML for debugging
            html = self.page.content()
            with open("debug_dump.html", "w", encoding="utf-8") as f:
                f.write(html)
            raise AssertionError(
                "Expected text 'Rules disabled until' not found. Page dumped to debug_dump.html"
            ) from e

        # Check the database to verify rules are actually disabled
        conn = sqlite3.connect(self.test_db_name)
        conn.row_factory = sqlite3.Row
        disabled_until = rules_engine.all_rules_disabled_until(conn)
        # logger.info("disabled_until=%s", disabled_until)
        assert disabled_until != 0

        current_time = time.time()
        min_expected_time = current_time + (expected_minutes * 60)

        # logger.info("Current time: %s", current_time)
        # logger.info("Disabled until: %s", disabled_until)
        # logger.info("Min expected time: %s", min_expected_time)

        assert disabled_until >= min_expected_time, (
            f"Rules should be disabled until at least {min_expected_time}, but got {disabled_until}"
        )
        conn.close()

    def check_database_rules_enabled(self) -> None:
        """Check that the database shows rules are enabled"""

        conn = sqlite3.connect(self.test_db_name)
        conn.row_factory = sqlite3.Row
        disabled_until = rules_engine.all_rules_disabled_until(conn)
        assert disabled_until == 0, (
            "Rules should be enabled (disabled_until=0), but got {disabled_until}"
        )
        conn.close()
