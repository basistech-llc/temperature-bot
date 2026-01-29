"""
End-to-end browser tests for chart page (DOM errors, exclusion-set behavior).
Fan speed and page-load checks were migrated to pytest (test_temporal_quantifiers, test_endpoints).
"""

import os
import time
import logging
import threading

import requests
import pytest
from playwright.sync_api import sync_playwright, expect

from conftest import test_database_conn_with_test_data, skip_on_github  # noqa: F401,F811  # pylint: disable=unused-import
from app.main import app

logger = logging.getLogger(__name__)


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


@pytest.mark.skipif(os.getenv("SKIP_BROWSER_TEST"), reason="SKIP_BROWSER_TEST is set")
@skip_on_github
def test_chart_page_no_dom_errors(test_database_conn_with_test_data):  # noqa: F811  # pylint: disable=unused-argument
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
):  # noqa: F811  # pylint: disable=unused-argument
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
):  # noqa: F811  # pylint: disable=unused-argument
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
