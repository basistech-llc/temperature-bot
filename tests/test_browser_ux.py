"""
End-to-end browser test for fan speed controls.
Tests the complete user experience from clicking buttons to database updates.

NOTE: AQI (air quality index) is not being tested in this file and can be ignored for now.
"""
import os
import json
import sqlite3
import time
import logging
import threading
from unittest.mock import patch
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, Page, expect

from fixtures import client, skip_on_github  # noqa: F401  # pylint: disable=unused-import
from app import ae200
from app import db
from app.paths import TEST_DATA_DIR

from app.main import app


logger = logging.getLogger(__name__)

# Disable websockets debug
@pytest.fixture(autouse=True)
def reduce_websockets_logging():
    logging.getLogger("websockets.client").setLevel(logging.INFO)


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
        logger.debug("row=%s",row)
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

    def verify_database_speed(self, expected_speed: int):
        """Verify that the database has been updated with the expected speed"""
        device_id = self.get_broadway_south_device_id()

        with sqlite3.connect(self.test_db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Check the most recent changelog entry
            cursor.execute("""
                SELECT new_value, agent FROM changelog
                WHERE device_id = ?
                ORDER BY changelog_id DESC
                LIMIT 1
            """, (device_id,))
            changelog_entry = cursor.fetchone()

            assert changelog_entry is not None, "No changelog entry found"
            assert changelog_entry['new_value'] == str(expected_speed), \
                f"Expected speed {expected_speed}, got {changelog_entry['new_value']}"
            assert changelog_entry['agent'] == 'web', \
                f"Expected agent 'web', got {changelog_entry['agent']}"

            # Check the most recent devlog entry
            cursor.execute("""
                SELECT status_json FROM devlog
                WHERE device_id = ?
                ORDER BY logtime DESC
                LIMIT 1
            """, (device_id,))
            devlog_entry = cursor.fetchone()

            assert devlog_entry is not None, "No devlog entry found"
            status_data = json.loads(devlog_entry['status_json'])
            extracted_status = ae200.extract_status(status_data)
            assert extracted_status['drive_speed_val'] == expected_speed, \
                f"Expected drive_speed_val {expected_speed}, got {extracted_status['drive_speed_val']}"


# Set this flag to True to enable AQI testing, False to disable
TEST_AQI = False

# pylint: disable=too-many-arguments, disable=too-many-positional-arguments, disable=too-many-statements
@skip_on_github
@patch("app.ae200.get_device_info")
@patch("app.ae200.set_fan_speed")
@patch("app.ae200.get_devices")
@patch("app.weather.get_weather_data")
@patch("app.airnow.get_aqi_sync")
def test_browser_fan_speed_controls(
    mock_get_aqi,
    mock_get_weather_data,
    mock_get_devices,
    mock_set_fan_speed,
    mock_get_device_info,
    client     # noqa: F811 # pylint: disable=unused-argument
):
    """
    End-to-end test that:
    1. Clicks fan speed 0 for Broadway South and verifies database and UI updates
    2. Clicks fan speed 4 for Broadway South and verifies database and UI updates
    3. Clicks fan speed 1 for Broadway South and verifies database and UI updates
    """

    # Set up test database with Broadway South device
    test_db_name = os.environ['TEST_DB_NAME']
    BROADWAY_SOUTH = 10

    with sqlite3.connect(test_db_name) as test_conn:
        test_conn.row_factory = sqlite3.Row
        device_id = db.get_or_create_device_id(test_conn, "Broadway South")
        c = test_conn.cursor()
        c.execute("UPDATE devices set ae200_device_id=? where device_id=?", (BROADWAY_SOUTH, device_id))

        # Add initial devlog entry for Broadway South so it appears in status API
        current_time = int(time.time())
        initial_status = {
            "Drive": "ON",
            "FanSpeed": "LOW",
            "InletTemp": "24.0"
        }
        db.insert_devlog_entry(
            test_conn,
            device_id=device_id,
            temp=24.0,
            statusdict=initial_status,
            logtime=current_time,
            force=True
        )
        test_conn.commit()

    # Set up mocked return values
    with open(Path(TEST_DATA_DIR) / 'get_devices.json') as f:
        mock_get_devices.return_value = json.load(f)

    # Mock weather and AQI data
    mock_get_aqi.return_value = {"value": 45, "color": "#00e400", "name": "Good"}
    mock_get_weather_data.return_value = {
        "current": {"temperature": 72, "conditions": "Sunny"},
        "forecast": []
    }

    # Mock device info responses for different speeds
    def mock_device_info_response(speed_name):
        with open(Path(TEST_DATA_DIR) / 'get_device_10.json') as f:
            dev10 = json.load(f)
            dev10['FanSpeed'] = speed_name
            return dev10

    # Start the Flask app in a separate thread

    def run_app():
        app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_app, daemon=True)
    server_thread.start()

    # Give the server time to start
    time.sleep(3)

    try:
        with sync_playwright() as p:
            # Launch browser
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Navigate to the application
            page.goto('http://127.0.0.1:5001/')

            # Create helper for browser operations
            helper = BrowserTestHelper(page, test_db_name)

            # Wait for the grid to load
            helper.wait_for_grid_to_load()

            # Test 1: Click fan speed 0 (OFF)
            logger.info("Testing fan speed 0 (OFF)")

            # Set up mock for speed 0
            mock_get_device_info.return_value = mock_device_info_response("OFF")

            # Click fan speed 0
            helper.click_fan_speed(0)

            # Wait for the request to complete
            page.wait_for_timeout(2000)

            # Verify radio button is selected
            helper.verify_radio_selected(0)

            # Verify other speeds are not selected
            for speed in [1, 2, 3, 4]:
                helper.verify_radio_not_selected(speed)

            # Verify database was updated
            helper.verify_database_speed(0)

            # Verify the mock was called correctly
            mock_set_fan_speed.assert_called_with(BROADWAY_SOUTH, 0)
            mock_get_device_info.assert_called_with(BROADWAY_SOUTH)

            # Test 2: Click fan speed 4 (HIGH)
            logger.info("Testing fan speed 4 (HIGH)")

            # Set up mock for speed 4
            mock_get_device_info.return_value = mock_device_info_response("HIGH")

            # Click fan speed 4
            helper.click_fan_speed(4)

            # Wait for the request to complete
            page.wait_for_timeout(2000)

            # Verify radio button is selected
            helper.verify_radio_selected(4)

            # Verify other speeds are not selected
            for speed in [0, 1, 2, 3]:
                helper.verify_radio_not_selected(speed)

            # Verify database was updated
            helper.verify_database_speed(4)

            # Verify the mock was called correctly
            mock_set_fan_speed.assert_called_with(BROADWAY_SOUTH, 4)

            # Test 3: Click fan speed 1 (LOW)
            logger.info("Testing fan speed 1 (LOW)")

            # Set up mock for speed 1
            mock_get_device_info.return_value = mock_device_info_response("LOW")

            # Click fan speed 1
            helper.click_fan_speed(1)

            # Wait for the request to complete
            page.wait_for_timeout(2000)

            # Verify radio button is selected
            helper.verify_radio_selected(1)

            # Verify other speeds are not selected
            for speed in [0, 2, 3, 4]:
                helper.verify_radio_not_selected(speed)

            # Verify database was updated
            helper.verify_database_speed(1)

            # Verify the mock was called correctly
            mock_set_fan_speed.assert_called_with(BROADWAY_SOUTH, 1)

            # Verify total number of calls
            assert mock_set_fan_speed.call_count == 3, f"Expected 3 calls, got {mock_set_fan_speed.call_count}"
            assert mock_get_device_info.call_count == 3, f"Expected 3 calls, got {mock_get_device_info.call_count}"

            browser.close()

    except Exception as e:
        logger.error("Browser test failed: %s",e)
        raise
    finally:
        # Clean up - the server thread will be terminated when the process ends
        pass


# pylint: disable=unused-argument
@skip_on_github
@patch("app.ae200.get_device_info")
@patch("app.ae200.set_fan_speed")
@patch("app.ae200.get_devices")
@patch("app.weather.get_weather_data")
@patch("app.airnow.get_aqi_sync")
def test_browser_page_loads_correctly(
    mock_get_aqi,
    mock_get_weather_data,
    mock_get_devices,
    mock_set_fan_speed,
    mock_get_device_info,
    client  # noqa: F811
):
    """Test that the browser page loads correctly with all elements"""

    # Set up test database
    test_db_name = os.environ['TEST_DB_NAME']
    BROADWAY_SOUTH = 10

    with sqlite3.connect(test_db_name) as test_conn:
        test_conn.row_factory = sqlite3.Row
        device_id = db.get_or_create_device_id(test_conn, "Broadway South")
        c = test_conn.cursor()
        c.execute("UPDATE devices set ae200_device_id=? where device_id=?", (BROADWAY_SOUTH, device_id))

        # Add initial devlog entry for Broadway South so it appears in status API
        current_time = int(time.time())
        initial_status = {
            "Drive": "ON",
            "FanSpeed": "LOW",
            "InletTemp": "24.0"
        }
        db.insert_devlog_entry(
            test_conn,
            device_id=device_id,
            temp=24.0,
            statusdict=initial_status,
            logtime=current_time,
            force=True
        )
        test_conn.commit()

    # Set up mocked return values
    with open(Path(TEST_DATA_DIR) / 'get_devices.json') as f:
        mock_get_devices.return_value = json.load(f)

    with open(Path(TEST_DATA_DIR) / 'get_device_10.json') as f:
        mock_get_device_info.return_value = json.load(f)

    mock_get_aqi.return_value = {"value": 45, "color": "#00e400", "name": "Good"}
    mock_get_weather_data.return_value = {
        "current": {"temperature": 72, "conditions": "Sunny"},
        "forecast": []
    }

    # Start the Flask app in a separate thread

    def run_app():
        app.run(host='127.0.0.1', port=5002, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_app, daemon=True)
    server_thread.start()

    # Give the server time to start
    time.sleep(3)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Navigate to the application
            page.goto('http://127.0.0.1:5002/')

            # Verify page title
            expect(page).to_have_title("Unit Speed Control")

            # Verify main heading
            expect(page.locator("h1")).to_contain_text("1070 Broadway")

            # Wait for the grid to load
            page.wait_for_selector('table.pure-table', timeout=10000)

            # Verify Broadway South row exists
            broadway_row = page.locator('tr:has-text("Broadway South")')
            expect(broadway_row).to_be_visible()

            # Verify fan speed radio buttons exist for Broadway South
            helper = BrowserTestHelper(page, test_db_name)
            device_id = helper.get_broadway_south_device_id()

            for speed in [0, 1, 2, 3, 4]:
                radio = page.locator(f'#radio-{device_id}-{speed}')
                expect(radio).to_be_visible()
                expect(radio).to_have_attribute('type', 'radio')
                expect(radio).to_have_value(str(speed))

            # Verify AQI section exists
            expect(page.locator('#aqi')).to_be_visible()
            if TEST_AQI:
                expect(page.locator('#aqi-value')).to_contain_text("45")
                expect(page.locator('#aqi-name')).to_contain_text("Good")

            # Verify weather section exists
            expect(page.locator('#weather')).to_be_visible()
            expect(page.locator('#weather')).to_contain_text("72°F")
            expect(page.locator('#weather')).to_contain_text("Sunny")

            # Verify log table exists
            expect(page.locator('#log-table')).to_be_visible()

            browser.close()

    except Exception as e:
        logger.error("Browser page load test failed: %s",e)
        raise
    finally:
        # Clean up
        pass
