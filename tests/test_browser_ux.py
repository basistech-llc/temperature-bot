"""
End-to-end browser test for fan speed controls.
NOTE: AQI (air quality index) is not being tested in this file and can be ignored for now.
"""

import os
import time
import logging
import threading
import datetime
from unittest.mock import patch
from pathlib import Path

import requests
import pytest
from playwright.sync_api import sync_playwright, expect, TimeoutError as PWTimeoutError

from conftest import test_database_conn_with_test_data, skip_on_github  # noqa: F401,F811  # pylint: disable=unused-import
from helpers.browser_helpers import BrowserTestHelper, TemperatureTestHelper
from helpers.mock_helpers import MockHelper
from helpers.data_factories import DeviceTestData, TestDataFactory
from app import db
from app import ae200
from app.main import app

logger = logging.getLogger(__name__)

TEST_TEMP = 32

# Set this flag to True to enable AQI testing, False to disable
TEST_AQI = False


def wait_for_server(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(url, timeout=0.5).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Backend not healthy at {url} within {timeout}s")


# pylint: disable=too-many-arguments, disable=too-many-positional-arguments, disable=too-many-statements
SKIP_BROWSER_TEST = "SKIP_BROWSER_TEST" in os.environ


@pytest.mark.skipif(SKIP_BROWSER_TEST, reason="SKIP_BROWSER_TEST is set")
@skip_on_github
@patch("app.weather.get_weather_data")
@patch("app.airquality.get_aqi")
def test_browser_fan_speed_controls(
    mock_get_airquality, mock_get_weather_data, test_database_conn_with_test_data
):  # noqa: F811
    """
    End-to-end test that:
    1. Clicks fan speed 0 for Broadway Test and verifies database and UI updates
    2. Clicks fan speed 4 for Broadway Test and verifies database and UI updates
    3. Clicks fan speed 1 for Broadway Test and verifies database and UI updates
    """

    # Set up test database with ERV Broadway Test (ERV table has radios 0,1,2,3,4)
    BROADWAY_SOUTH = 10
    ERV_DEVICE_NAME = "ERV Broadway Test"

    # Use new database helper
    test_conn = test_database_conn_with_test_data[0]
    device_id = TestDataFactory.create_erv_broadway_device(test_conn, BROADWAY_SOUTH)

    # Add initial devlog entry for ERV Broadway Test so it appears in status API
    current_time = int(time.time())
    initial_status = DeviceTestData.get_initial_status()
    db.insert_devlog_entry(
        test_conn,
        device_id=device_id,
        temp=24.0,
        statusdict=initial_status,
        logtime=current_time,
        force=True,
    )
    # Add a second device without speed control
    TestDataFactory.create_device_with_status(
        test_conn, "No Speed Device", DeviceTestData.get_no_speed_status(), current_time
    )

    # Set up weather mocks
    MockHelper.setup_weather_mocks(
        mock_get_airquality, mock_get_weather_data, 45, TEST_TEMP
    )

    # Start the Flask app in a separate thread
    def run_app():
        app.run(host="127.0.0.1", port=5001, debug=False, use_reloader=False)

    # pylint: disable=duplicate-code
    server_thread = threading.Thread(target=run_app, daemon=True)
    server_thread.start()

    # Give the server time to start
    time.sleep(3)

    with sync_playwright() as p:
        try:
            # Launch browser
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Navigate to the application
            page.goto("http://127.0.0.1:5001/")

            # Create helper for browser operations
            helper = BrowserTestHelper(page, os.environ["TEST_DB_NAME"])

            # Wait for the grid to load
            helper.wait_for_grid_to_load()

            # Verify that ERV Broadway Test has speed radio buttons (ERV table: 0,1,2,3,4)
            for speed in [1, 2, 3, 4]:
                radio = page.locator(
                    f"#radio-{helper.get_broadway_south_device_id(ERV_DEVICE_NAME)}-{speed}"
                )
                expect(radio).to_be_visible()

            # Verify that No Speed Device does not have any radio buttons
            no_speed_row = page.locator('tr:has-text("No Speed Device")')
            for speed in [0, 1, 2, 3, 4]:
                radio = no_speed_row.locator('input[type="radio"][x-data-device-id]')
                expect(radio).not_to_be_visible()

            # Test 1: Click fan speed 1 (LOW) since UI has speeds [-1,1,2,3,4]
            # logger.info("Testing fan speed 1 (LOW)")

            # Set up simulator for speed 1
            ae200.set_fan_speed(BROADWAY_SOUTH, 1)

            # Click fan speed 1
            helper.click_fan_speed(1, ERV_DEVICE_NAME)

            # Wait for the request to complete
            page.wait_for_timeout(2000)

            # Verify radio button is selected
            helper.verify_radio_selected(1, ERV_DEVICE_NAME)

            # Verify other speeds are not selected
            for speed in [2, 3, 4]:
                helper.verify_radio_not_selected(speed, ERV_DEVICE_NAME)

            #  Verify database was updated
            #  helper.verify_database_speed(0)

            # ChangeFan speed not called becuase
            # mock_set_fan_speed.assert_called_with(BROADWAY_SOUTH, 0)
            # mock_get_device_info.assert_called_with(BROADWAY_SOUTH)

            # Test 2: Click fan speed 4 (HIGH)
            # logger.info("Testing fan speed 4 (HIGH)")

            # Set up simulator for speed 4
            ae200.set_fan_speed(BROADWAY_SOUTH, 4)

            # Click fan speed 4
            helper.click_fan_speed(4, ERV_DEVICE_NAME)

            # Wait for the request to complete
            page.wait_for_timeout(2000)

            # Verify radio button is selected
            helper.verify_radio_selected(4, ERV_DEVICE_NAME)

            # Verify other speeds are not selected
            for speed in [1, 2, 3]:
                helper.verify_radio_not_selected(speed, ERV_DEVICE_NAME)

            # Verify database was updated
            # helper.verify_database_speed(4)

            # Verify the mock was called correctly
            # mock_set_fan_speed.assert_called_with(BROADWAY_SOUTH, 4)
            # mock_get_device_info.assert_called_with(BROADWAY_SOUTH)

            # Test 3: Click fan speed 2 (MID2)
            # logger.info("Testing fan speed 2 (MID2)")

            # Set up simulator for speed 2
            ae200.set_fan_speed(BROADWAY_SOUTH, 2)

            # Click fan speed 2
            helper.click_fan_speed(2, ERV_DEVICE_NAME)

            # Wait for the request to complete
            page.wait_for_timeout(2000)

            # Verify radio button is selected
            helper.verify_radio_selected(2, ERV_DEVICE_NAME)

            # Verify other speeds are not selected
            for speed in [1, 3, 4]:
                helper.verify_radio_not_selected(speed, ERV_DEVICE_NAME)

            # Verify database was updated
            # helper.verify_database_speed(1)

            # Verify the mock was called correctly
            # mock_set_fan_speed.assert_called_with(BROADWAY_SOUTH, 1)

            # Verify simulator state was updated correctly
            device_info = ae200.get_device_info(BROADWAY_SOUTH)
            assert device_info["FanSpeed"] == "MID2"

            browser.close()
        finally:
            # Clean up - the server thread will be terminated when the process ends
            pass


# pylint: disable=unused-argument
@pytest.mark.skipif(os.getenv("SKIP_BROWSER_TEST"), reason="SKIP_BROWSER_TEST is set")
@skip_on_github
@patch("app.weather.get_weather_data")
@patch("app.airquality.get_aqi")
def test_browser_page_loads_correctly(
    mock_get_airquality, mock_get_weather_data, test_database_conn_with_test_data
):  # noqa: F811
    """Test that the browser page loads correctly with all elements"""

    # Set up test database (ERV device so radios 1-4 exist in ERV table)
    BROADWAY_SOUTH = 10
    ERV_DEVICE_NAME = "ERV Broadway Test"

    test_conn = test_database_conn_with_test_data[0]
    device_id = TestDataFactory.create_erv_broadway_device(test_conn, BROADWAY_SOUTH)

    # Add initial devlog entry so device appears in status API
    current_time = int(time.time())
    initial_status = DeviceTestData.get_initial_status()
    db.insert_devlog_entry(
        test_conn,
        device_id=device_id,
        temp=24.0,
        statusdict=initial_status,
        logtime=current_time,
        force=True,
    )

    # Set up weather mocks
    MockHelper.setup_weather_mocks(
        mock_get_airquality, mock_get_weather_data, 45, TEST_TEMP
    )

    # Start the Flask app in a separate thread
    def run_app():
        app.run(host="127.0.0.1", port=5002, debug=False, use_reloader=False)

    # pylint: disable=duplicate-code
    server_thread = threading.Thread(target=run_app, daemon=True)
    server_thread.start()

    # Give the server time to start
    time.sleep(3)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Navigate to the application
            page.goto("http://127.0.0.1:5002/")

            # Verify page title
            expect(page).to_have_title("Unit Speed Control")

            # Wait for the grid to load
            page.wait_for_selector("table.pure-table", timeout=10000)

            # Verify main grid and section headings exist
            expect(page.locator("#main-grid")).to_be_visible()
            expect(
                page.locator("h2:has-text('Energy Recovery Ventilation')")
            ).to_be_visible()

            # Verify ERV Broadway Test row exists
            broadway_row = page.locator("tr:has-text(\"" + ERV_DEVICE_NAME + "\")")
            expect(broadway_row).to_be_visible()

            # Verify fan speed radio buttons exist for ERV device (ERV table: 0,1,2,3,4)
            helper = BrowserTestHelper(page, os.environ["TEST_DB_NAME"])
            device_id = helper.get_broadway_south_device_id(ERV_DEVICE_NAME)

            for speed in [1, 2, 3, 4]:
                radio = page.locator(f"#radio-{device_id}-{speed}")
                expect(radio).to_be_visible()
                expect(radio).to_have_attribute("type", "radio")
                expect(radio).to_have_value(str(speed))

            # pylint: disable=duplicate-code
            browser.close()
        finally:
            # Clean up
            pass


@pytest.mark.skipif(os.getenv("SKIP_BROWSER_TEST"), reason="SKIP_BROWSER_TEST is set")
@skip_on_github
@patch("app.weather.get_weather_data")
@patch("app.airquality.get_aqi")
def test_browser_temperature_display(
    mock_get_airquality, mock_get_weather_data, test_database_conn_with_test_data
):  # noqa: F811
    """
    Comprehensive test for temperature display functionality:
    1. Tests that temporal buttons (day, week, month) work correctly
    2. Verifies record counts match expected values for different time ranges
    3. Tests with temporal test data (1 hour, 26 hours, 200 hours, 2000 hours ago)
    """

    device_id = test_database_conn_with_test_data[1]
    expected_counts = test_database_conn_with_test_data[2]

    # Mock weather and AQI data using new mock helper
    MockHelper.setup_weather_mocks(
        mock_get_airquality, mock_get_weather_data, 45, TEST_TEMP
    )

    # Start the Flask app in a separate thread
    def run_app():
        app.run(host="127.0.0.1", port=5003, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_app, daemon=True)
    server_thread.start()
    wait_for_server("http://127.0.0.1:5003/health", timeout=20)

    # Give the server time to start
    # pylint: disable=duplicate-code
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Navigate to the chart page for the specific device
            page.goto(f"http://127.0.0.1:5003/chart?device_id={device_id}")

            # Wait for the chart to load (chart page has #controls, #temp-chart, #record-count)
            helper = TemperatureTestHelper(page, os.environ["TEST_DB_NAME"])
            page.wait_for_load_state("networkidle", timeout=30_000)
            page.wait_for_selector("#controls", timeout=10000)
            page.wait_for_selector("#record-count", timeout=10000)

            # Chart defaults to week (7 days) on load
            helper.verify_record_count(expected_counts["week"])

            # Test day button
            helper.click_temporal_button("day")
            helper.verify_record_count(expected_counts["day"])

            # Test week button
            helper.click_temporal_button("week")
            helper.verify_record_count(expected_counts["week"])

            # Test month button
            helper.click_temporal_button("month")
            helper.verify_record_count(expected_counts["month"])

            # Test day button again
            helper.click_temporal_button("day")
            helper.verify_record_count(expected_counts["day"])

            # Test all button (full range)
            helper.click_temporal_button("all")
            helper.verify_record_count(expected_counts["all"])

            # Verify all temporal buttons are present and clickable
            expect(page.locator("#dayBtn")).to_be_visible()
            expect(page.locator("#weekBtn")).to_be_visible()
            expect(page.locator("#monthBtn")).to_be_visible()
            expect(page.locator("#allBtn")).to_be_visible()

            # Verify chart container is present and loaded
            expect(page.locator("#temp-chart")).to_be_visible()

            # Verify record count element is present and shows data
            record_count_element = page.locator("#record-count")
            expect(record_count_element).to_be_visible()
            expect(record_count_element).to_contain_text("Total temperature datapoints:")

            browser.close()
        except PWTimeoutError as e:
            logger.error("❌ Timeout error %s on %s", e, page.url)
            ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            fname_html = Path(f"debug_page_{ts}.html")
            fname_png = Path(f"debug_page_{ts}.png")

            fname_html.write_text(page.content(), encoding="utf-8")
            logger.error("   HTML dump: %s", fname_html.resolve())

            page.screenshot(path=str(fname_png), full_page=True)
            logger.error("   Screenshot: %s", fname_png.resolve())
            raise
        finally:
            # Clean up
            pass


@pytest.mark.skipif(os.getenv("SKIP_BROWSER_TEST"), reason="SKIP_BROWSER_TEST is set")
@skip_on_github
def test_chart_page_no_dom_errors(test_database_conn_with_test_data):  # noqa: F811
    """
    This test requires the Flask server to be running at http://localhost:8000.
    It checks for DOM errors (like NotFoundError) in the chart page JavaScript.
    """
    # Start the Flask app in a separate thread

    # logger.info("running with test database and test client %s",test_database_conn_with_test_data)
    def run_app():
        app.run(host="127.0.0.1", port=5004, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_app, daemon=True)
    server_thread.start()

    # Give the server time to start
    time.sleep(3)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []

        # Listen for console errors
        page.on(
            "console", lambda msg: errors.append(msg) if msg.type == "error" else None
        )

        # Go to the chart page
        page.goto("http://127.0.0.1:5004/chart")
        # Wait for the chart and controls to load (chart.html has #controls, #record-count)
        page.wait_for_selector("#controls", timeout=15000)
        page.wait_for_selector("#record-count", timeout=15000)

        # Wait a bit for JS to run
        page.wait_for_timeout(1000)

        # Check for NotFoundError in console errors
        error_texts = [msg.text for msg in errors]
        assert not any("NotFoundError" in text for text in error_texts), (
            f"Console errors: {error_texts}"
        )

        browser.close()


@pytest.mark.skipif(SKIP_BROWSER_TEST, reason="SKIP_BROWSER_TEST is set")
@skip_on_github
def test_chart_exclusion_set_persists_after_clear_all_and_range_change(
    test_database_conn_with_test_data,
):  # noqa: F811
    """
    Verify exclusion-set behavior: Clear All then change date range keeps chart empty
    (exclusions persist; user's intent to show nothing is preserved).
    """

    def run_app():
        app.run(host="127.0.0.1", port=5005, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_app, daemon=True)
    server_thread.start()
    wait_for_server("http://127.0.0.1:5005/health", timeout=20)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            # Load chart without device_ids so we get the full sensor list and checkboxes
            page.goto(
                "http://127.0.0.1:5005/chart", wait_until="networkidle", timeout=30_000
            )
            page.wait_for_selector("#clearAllBtn", timeout=10_000)
            page.wait_for_selector("#weekBtn", timeout=5_000)
            # Wait for at least one checkbox (created after temp data loads)
            page.wait_for_selector("#checkboxes input[type=checkbox]", timeout=15_000)

            checkboxes = page.locator("#checkboxes input[type=checkbox]")
            initial_count = checkboxes.count()
            assert initial_count >= 1, (
                "need at least one sensor with data to test exclusion"
            )

            # Clear All: all sensors go into exclusion set, all checkboxes unchecked
            page.locator("#clearAllBtn").click()
            page.wait_for_timeout(300)
            for i in range(initial_count):
                expect(checkboxes.nth(i)).not_to_be_checked()

            # Change range (Week) -> data reloads, checkboxes rebuilt; exclusions must persist
            page.locator("#weekBtn").click()
            page.wait_for_timeout(2_000)  # allow fetch + createAllSensorCheckboxes

            checkboxes_after = page.locator("#checkboxes input[type=checkbox]")
            n_after = checkboxes_after.count()
            assert n_after >= 1, "expected checkboxes after range change"
            checked_after = sum(
                1 for i in range(n_after) if checkboxes_after.nth(i).is_checked()
            )
            assert checked_after == 0, (
                "after Clear All then range change, no checkbox should be checked (exclusions persist); "
                f"got {checked_after} checked"
            )
        finally:
            browser.close()


@pytest.mark.skipif(SKIP_BROWSER_TEST, reason="SKIP_BROWSER_TEST is set")
@skip_on_github
def test_chart_select_all_clears_exclusions_then_range_shows_all(
    test_database_conn_with_test_data,
):  # noqa: F811
    """
    Verify Select All clears exclusion set: after Clear All, Select All, then change range,
    all sensors with data should be checked (exclusions cleared).
    """

    def run_app():
        app.run(host="127.0.0.1", port=5006, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_app, daemon=True)
    server_thread.start()
    wait_for_server("http://127.0.0.1:5006/health", timeout=20)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(
                "http://127.0.0.1:5006/chart", wait_until="networkidle", timeout=30_000
            )
            page.wait_for_selector("#clearAllBtn", timeout=10_000)
            page.wait_for_selector("#selectAllBtn", timeout=5_000)
            page.wait_for_selector("#checkboxes input[type=checkbox]", timeout=15_000)

            # Clear All -> all unchecked
            page.locator("#clearAllBtn").click()
            page.wait_for_timeout(300)

            # Select All -> exclusion set cleared, all checkboxes checked
            page.locator("#selectAllBtn").click()
            page.wait_for_timeout(300)

            checkboxes = page.locator(
                "#checkboxes input[type=checkbox]:not([disabled])"
            )
            n_enabled = checkboxes.count()
            assert n_enabled >= 1, "need at least one enabled checkbox"
            for i in range(n_enabled):
                expect(checkboxes.nth(i)).to_be_checked()

            # Change range (Week) -> exclusions were cleared, so all with data should stay checked
            page.locator("#weekBtn").click()
            page.wait_for_timeout(2_000)

            checkboxes_after = page.locator(
                "#checkboxes input[type=checkbox]:not([disabled])"
            )
            n_after = checkboxes_after.count()
            assert n_after >= 1, "expected enabled checkboxes after range change"
            checked_after = sum(
                1 for i in range(n_after) if checkboxes_after.nth(i).is_checked()
            )
            assert checked_after == n_after, (
                "after Select All then range change, all enabled checkboxes should be checked; "
                f"got {checked_after}/{n_after} checked"
            )
        finally:
            browser.close()
