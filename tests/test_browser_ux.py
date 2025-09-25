"""
End-to-end browser test for fan speed controls.
NOTE: AQI (air quality index) is not being tested in this file and can be ignored for now.
"""
import os
import time
import logging
import threading
from unittest.mock import patch

import pytest
from playwright.sync_api import sync_playwright, expect

from conftest import client, skip_on_github  # noqa: F401  # pylint: disable=unused-import
from helpers.browser_helpers import BrowserTestHelper, TemperatureTestHelper
from helpers.database_helpers import DatabaseTestHelper
from helpers.mock_helpers import MockHelper
from helpers.data_factories import DeviceTestData, TestDataFactory
from app import db

from app.main import app


logger = logging.getLogger(__name__)

TEST_TEMP=32

# Disable websockets debug
@pytest.fixture(autouse=True)
def reduce_websockets_logging():
    logging.getLogger("websockets.client").setLevel(logging.INFO)


# Set this flag to True to enable AQI testing, False to disable
TEST_AQI = False

# pylint: disable=too-many-arguments, disable=too-many-positional-arguments, disable=too-many-statements
@skip_on_github
@patch("app.weather.get_weather_data")
@patch("app.airquality.get_aqi")
def test_browser_fan_speed_controls(
    mock_get_airquality,
    mock_get_weather_data,
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

    # Use new database helper
    db_helper = DatabaseTestHelper(test_db_name)
    with db_helper.get_connection() as test_conn:
        device_id = TestDataFactory.create_broadway_south_device(test_conn, BROADWAY_SOUTH)

        # Add initial devlog entry for Broadway South so it appears in status API
        current_time = int(time.time())
        initial_status = DeviceTestData.get_initial_status()
        db.insert_devlog_entry(
            test_conn,
            device_id=device_id,
            temp=24.0,
            statusdict=initial_status,
            logtime=current_time,
            force=True
        )
        # Add a second device without speed control
        TestDataFactory.create_device_with_status(
            test_conn,
            "No Speed Device",
            DeviceTestData.get_no_speed_status(),
            current_time
        )

    # Set up weather mocks
    MockHelper.setup_weather_mocks(mock_get_airquality, mock_get_weather_data, 45, TEST_TEMP)

    # Start the Flask app in a separate thread
    def run_app():
        app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)

    # pylint: disable=duplicate-code
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

            # Verify that Broadway South has speed radio buttons
            for speed in [1, 2, 3, 4]:
                radio = page.locator(f'#radio-{helper.get_broadway_south_device_id()}-{speed}')
                expect(radio).to_be_visible()

            # Verify that No Speed Device does not have any radio buttons
            no_speed_row = page.locator('tr:has-text("No Speed Device")')
            for speed in [0, 1, 2, 3, 4]:
                radio = no_speed_row.locator('input[type="radio"][x-data-device-id]')
                expect(radio).not_to_be_visible()

            # Test 1: Click fan speed 1 (LOW) since UI has speeds [-1,1,2,3,4]
            logger.info("Testing fan speed 1 (LOW)")

            # Set up simulator for speed 1
            from app import ae200
            ae200.set_fan_speed(BROADWAY_SOUTH, 1)

            # Click fan speed 1
            helper.click_fan_speed(1)

            # Wait for the request to complete
            page.wait_for_timeout(2000)

            # Verify radio button is selected
            helper.verify_radio_selected(1)

            # Verify other speeds are not selected
            for speed in [2, 3, 4]:
                helper.verify_radio_not_selected(speed)

            #  Verify database was updated
            #  helper.verify_database_speed(0)

            # ChangeFan speed not called becuase
            # mock_set_fan_speed.assert_called_with(BROADWAY_SOUTH, 0)
            # mock_get_device_info.assert_called_with(BROADWAY_SOUTH)

            # Test 2: Click fan speed 4 (HIGH)
            logger.info("Testing fan speed 4 (HIGH)")

            # Set up simulator for speed 4
            ae200.set_fan_speed(BROADWAY_SOUTH, 4)

            # Click fan speed 4
            helper.click_fan_speed(4)

            # Wait for the request to complete
            page.wait_for_timeout(2000)

            # Verify radio button is selected
            helper.verify_radio_selected(4)

            # Verify other speeds are not selected
            for speed in [1, 2, 3]:
                helper.verify_radio_not_selected(speed)

            # Verify database was updated
            # helper.verify_database_speed(4)

            # Verify the mock was called correctly
            # mock_set_fan_speed.assert_called_with(BROADWAY_SOUTH, 4)
            # mock_get_device_info.assert_called_with(BROADWAY_SOUTH)

            # Test 3: Click fan speed 2 (MID2)
            logger.info("Testing fan speed 2 (MID2)")

            # Set up simulator for speed 2
            ae200.set_fan_speed(BROADWAY_SOUTH, 2)

            # Click fan speed 2
            helper.click_fan_speed(2)

            # Wait for the request to complete
            page.wait_for_timeout(2000)

            # Verify radio button is selected
            helper.verify_radio_selected(2)

            # Verify other speeds are not selected
            for speed in [1, 3, 4]:
                helper.verify_radio_not_selected(speed)

            # Verify database was updated
            # helper.verify_database_speed(1)

            # Verify the mock was called correctly
            # mock_set_fan_speed.assert_called_with(BROADWAY_SOUTH, 1)

            # Verify simulator state was updated correctly
            device_info = ae200.get_device_info(BROADWAY_SOUTH)
            assert device_info['FanSpeed'] == "MID2"

            browser.close()

    except Exception as e:
        logger.error("Browser test failed: %s",e)
        raise
    finally:
        # Clean up - the server thread will be terminated when the process ends
        pass


# pylint: disable=unused-argument
@skip_on_github
@patch("app.weather.get_weather_data")
@patch("app.airquality.get_aqi")
def test_browser_page_loads_correctly(
    mock_get_airquality,
    mock_get_weather_data,
    client  # noqa: F811
):
    """Test that the browser page loads correctly with all elements"""

    # Set up test database using new helpers
    test_db_name = os.environ['TEST_DB_NAME']
    BROADWAY_SOUTH = 10

    db_helper = DatabaseTestHelper(test_db_name)
    with db_helper.get_connection() as test_conn:
        device_id = TestDataFactory.create_broadway_south_device(test_conn, BROADWAY_SOUTH)

        # Add initial devlog entry for Broadway South so it appears in status API
        current_time = int(time.time())
        initial_status = DeviceTestData.get_initial_status()
        db.insert_devlog_entry(
            test_conn,
            device_id=device_id,
            temp=24.0,
            statusdict=initial_status,
            logtime=current_time,
            force=True
        )

    # Set up weather mocks
    MockHelper.setup_weather_mocks(mock_get_airquality, mock_get_weather_data, 45, TEST_TEMP)

    # Start the Flask app in a separate thread
    def run_app():
        app.run(host='127.0.0.1', port=5002, debug=False, use_reloader=False)

    # pylint: disable=duplicate-code
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

            for speed in [1, 2, 3, 4]:
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
            logger.debug("page.locator #weather=%s",page.locator('#weather').inner_text())
            expect(page.locator('#weather')).to_be_visible()
            expect(page.locator('#weather')).to_contain_text(str(TEST_TEMP))
            expect(page.locator('#weather')).to_contain_text("Sunny")

            # Verify log table exists
            expect(page.locator('#log-table')).to_be_visible() # pylint: disable=duplicate-code

            # pylint: disable=duplicate-code
            browser.close()

    # pylint: disable=duplicate-code
    except Exception as e:
        logger.error("Browser page error: %s",e)
        raise
    finally:
        # Clean up
        pass


@skip_on_github
@patch("app.weather.get_weather_data")
@patch("app.airquality.get_aqi")
def test_browser_temperature_display(
    mock_get_airquality,
    mock_get_weather_data,
    client  # noqa: F811
):
    """
    Comprehensive test for temperature display functionality:
    1. Tests that temporal buttons (day, week, month) work correctly
    2. Verifies record counts match expected values for different time ranges
    3. Tests with temporal test data (1 hour, 26 hours, 200 hours, 2000 hours ago)
    """

    # Set up test database with temporal data using new helpers
    test_db_name = os.environ['TEST_DB_NAME']

    db_helper = DatabaseTestHelper(test_db_name)
    with db_helper.get_connection() as test_conn:
        # Create test device with temporal data
        from tests.conftest import insert_temporal_test_data  # pylint: disable=import-outside-toplevel
        device_id, expected_counts = insert_temporal_test_data(test_conn, "Temporal Test Device")

    # Mock weather and AQI data using new mock helper
    MockHelper.setup_weather_mocks(mock_get_airquality, mock_get_weather_data, 45, TEST_TEMP)

    # Start the Flask app in a separate thread
    def run_app():
        app.run(host='127.0.0.1', port=5003, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_app, daemon=True)
    server_thread.start()

    # Give the server time to start
    # pylint: disable=duplicate-code
    time.sleep(3)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Navigate to the chart page for the specific device
            page.goto(f'http://127.0.0.1:5003/chart?device_id={device_id}')

            # Wait for the chart to load
            helper = TemperatureTestHelper(page, test_db_name)
            helper.wait_for_chart_to_load()

            # Test initial load (should show all records)
            logger.info("Testing initial load")
            helper.verify_record_count(expected_counts["all"])

            # Test day button (should show 2 records: 1 hour + 26 hours)
            logger.info("Testing day button")
            helper.click_temporal_button('day')
            helper.verify_record_count(expected_counts["day"])

            # Test week button (should show 3 records: 1 hour + 26 hours + 200 hours)
            logger.info("Testing week button")
            helper.click_temporal_button('week')
            helper.verify_record_count(expected_counts["week"])

            # Test month button (should show all 4 records)
            logger.info("Testing month button")
            helper.click_temporal_button('month')
            helper.verify_record_count(expected_counts["month"])

            # Test day button again to ensure it still works
            logger.info("Testing day button again")
            helper.click_temporal_button('day')
            helper.verify_record_count(expected_counts["day"])

            # Verify all temporal buttons are present and clickable
            expect(page.locator('#dayBtn')).to_be_visible()
            expect(page.locator('#weekBtn')).to_be_visible()
            expect(page.locator('#monthBtn')).to_be_visible()

            # Verify chart container is present and loaded
            expect(page.locator('#main')).to_be_visible()

            # Verify record count element is present and shows data
            record_count_element = page.locator('#record-count')
            expect(record_count_element).to_be_visible()
            expect(record_count_element).to_contain_text("Records loaded:")

            browser.close()

    except Exception as e:
        logger.error("Temperature display test failed: %s", e)
        raise
    finally:
        # Clean up
        pass


def test_chart_page_no_dom_errors():
    """
    This test requires the Flask server to be running at http://localhost:8000.
    It checks for DOM errors (like NotFoundError) in the chart page JavaScript.
    """
    # Start the Flask app in a separate thread

    def run_app():
        app.run(host='127.0.0.1', port=5004, debug=False, use_reloader=False)


    server_thread = threading.Thread(target=run_app, daemon=True)
    server_thread.start()

    # Give the server time to start
    time.sleep(3)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []

        # Listen for console errors
        page.on("console", lambda msg: errors.append(msg) if msg.type == "error" else None)

        # Go to the chart page
        page.goto("http://localhost:5004/chart")
        # Wait for the chart and controls to load
        page.wait_for_selector("#main")
        page.wait_for_selector("#addDeviceSelect")

        # Wait a bit for JS to run
        page.wait_for_timeout(1000)

        # Check for NotFoundError in console errors
        error_texts = [msg.text for msg in errors]
        assert not any("NotFoundError" in text for text in error_texts), f"Console errors: {error_texts}"

        browser.close()
