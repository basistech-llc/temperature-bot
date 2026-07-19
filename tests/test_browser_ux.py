"""
End-to-end browser tests for chart page (DOM errors, exclusion-set behavior).
Fan speed and page-load checks were migrated to pytest (test_temporal_quantifiers, test_endpoints).
"""

import os
import time
import json
import logging
import threading
from urllib.parse import parse_qs, urlparse

import requests
import pytest
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

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


def seed_air_quality_temperature_device(conn, samples: int = 10) -> int:
    """Create one AQ device with enough recent temperature history for chart tests."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM devlog")
    cursor.execute("DELETE FROM devices")
    cursor.execute(
        "INSERT INTO devices (device_name, aqi_mon) VALUES (?, ?)",
        ("Airthings Browser Temp Probe", 1),
    )
    device_id = cursor.lastrowid
    now = int(time.time())
    for i in range(samples):
        temp_c = 22.0 + i / 10
        payload = {
            "co2": {"unit": "ppm", "value": 700 + i},
            "humidity": {"unit": "pct", "value": 45.0},
            "pm1": {"unit": "ug/m3", "value": 1.0},
            "pm25": {"unit": "ug/m3", "value": 2.0},
            "pressure": {"unit": "hPa", "value": 1010.0},
            "radonShortTermAvg": {"unit": "bq", "value": 75.0},
            "temp": {"unit": "c", "value": temp_c},
            "voc": {"unit": "ppb", "value": 120.0},
        }
        cursor.execute(
            """
            INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                device_id,
                now - (samples - i) * 60,
                60,
                round(temp_c * 10),
                json.dumps(payload),
            ),
        )
    conn.commit()
    return device_id


def is_temperature_response_for_device(response, base_url: str, device_id: int) -> bool:
    parsed_base = urlparse(base_url)
    parsed = urlparse(response.url)
    if parsed.netloc != parsed_base.netloc or parsed.path != "/api/v1/temperature":
        return False
    query = parse_qs(parsed.query)
    return query.get("device_ids") == [str(device_id)]


@pytest.mark.skipif(os.getenv("SKIP_BROWSER_TEST"), reason="SKIP_BROWSER_TEST is set")
@skip_on_github
def test_chart_page_no_dom_errors(test_database_conn_with_test_data):  # noqa: F811  # pylint: disable=unused-argument
    """
    This test requires the Flask server to be running at http://localhost:8000.
    It checks for DOM errors (like NotFoundError) in the temperature chart page JavaScript.
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

        # Go to the temperature chart page
        page.goto("http://127.0.0.1:5004/chart")
        # Wait for the chart and controls to load (temperature_chart.html has #controls, #record-count)
        page.wait_for_selector("#controls", timeout=15000)
        page.wait_for_selector("#record-count", timeout=15000)

        # Wait a bit for JS to run
        page.wait_for_timeout(1000)

        explanation = page.locator("#calculated-temperature-explanation")
        expect(explanation).to_be_hidden()
        page.locator('input[name="temperature-mode"][value="calculated"]').check()
        expect(explanation).to_be_visible()
        page.locator('input[name="temperature-mode"][value="raw"]').check()
        expect(explanation).to_be_hidden()

        expect(page.locator("#earlierDataBtn")).to_be_enabled()
        expect(page.locator("#laterDataBtn")).to_be_disabled()
        toolbox_features = page.evaluate(
            "Object.keys(tempChart.getOption().toolbox[0].feature)"
        )
        assert toolbox_features == ["myZoomIn", "myZoomOut", "dataZoom"]

        with page.expect_response(
            lambda response: "/api/v1/temperature" in response.url,
            timeout=15_000,
        ) as response_info:
            page.locator("#earlierDataBtn").click()
        shifted_payload = response_info.value.json()
        assert shifted_payload["has_earlier_data"] is True
        assert shifted_payload["has_later_data"] is True

        # Check for NotFoundError in console errors
        error_texts = [msg.text for msg in errors]
        assert not any("NotFoundError" in text for text in error_texts), (
            f"Console errors: {error_texts}"
        )

        browser.close()


@pytest.mark.skipif(SKIP_BROWSER_TEST, reason="SKIP_BROWSER_TEST is set")
def test_aqi_chart_first_render_and_selected_axis(
    test_database_conn_with_test_data,
):  # noqa: F811  # pylint: disable=unused-argument
    """AQI renders without console errors and owns the scale and grid when selected alone."""
    server = make_server("127.0.0.1", 0, app, threaded=True)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        wait_for_server(f"{base_url}/health", timeout=20)
        with sync_playwright() as playwright, playwright.chromium.launch(
            headless=True
        ) as browser:
            page = browser.new_page()
            errors = []
            page.on(
                "console",
                lambda message: errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.goto(f"{base_url}/chart_aqi", wait_until="networkidle")
            page.wait_for_function("aqiChart && aqiChart.getOption().series")
            chart_box = page.locator("#aqi-chart").bounding_box()
            assert chart_box is not None
            for name in ["PM2.5", "PM10", "O₃", "NO₂", "CO"]:
                point = page.evaluate(
                    """
                    (name) => {
                      const points = aqiChart.getZr().storage.getDisplayList()
                        .filter((item) => item.style?.text === name)
                        .map((item) => {
                          const rect = item.getBoundingRect();
                          const matrix = item.getComputedTransform()
                            || [1, 0, 0, 1, 0, 0];
                          const x = rect.x + rect.width / 2;
                          const y = rect.y + rect.height / 2;
                          return {
                            x: matrix[0] * x + matrix[2] * y + matrix[4],
                            y: matrix[1] * x + matrix[3] * y + matrix[5],
                          };
                        })
                        .filter((candidate) => candidate.y < 100)
                        .sort((left, right) => left.y - right.y);
                      if (!points.length) throw new Error(`Legend item ${name} not found`);
                      return points[0];
                    }
                    """,
                    name,
                )
                page.mouse.click(
                    chart_box["x"] + point["x"],
                    chart_box["y"] + point["y"],
                )
                page.wait_for_timeout(50)
            layout = page.evaluate(
                """
                () => {
                  const option = aqiChart.getOption();
                  return {
                    axes: option.yAxis.map((axis) => ({
                      name: axis.name,
                      show: axis.show,
                      offset: axis.offset,
                      splitLine: axis.splitLine.show,
                    })),
                    selected: option.legend[0].selected,
                  };
                }
                """
            )

            aqi_axis = next(axis for axis in layout["axes"] if axis["name"] == "AQI")
            assert aqi_axis == {
                "name": "AQI",
                "show": True,
                "offset": 0,
                "splitLine": True,
            }
            assert all(
                not axis["show"]
                for axis in layout["axes"]
                if axis["name"] != "AQI"
            )
            assert layout["selected"]["AQI"] is True
            assert not errors
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)


@pytest.mark.skipif(SKIP_BROWSER_TEST, reason="SKIP_BROWSER_TEST is set")
@skip_on_github
def test_air_quality_temperature_click_fetches_selected_device(
    test_database_conn_with_test_data,
):  # noqa: F811
    """Clicking an AQ temperature cell should chart only that device's data."""
    conn = test_database_conn_with_test_data[0]
    device_id = seed_air_quality_temperature_device(conn, samples=10)
    base_url = "http://127.0.0.1:5007"

    def run_app():
        app.run(host="127.0.0.1", port=5007, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_app, daemon=True)
    server_thread.start()
    wait_for_server(f"{base_url}/health", timeout=20)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(f"{base_url}/air-quality", wait_until="networkidle")
            row = page.locator("tr", has_text="Browser Temp Probe")
            temp_cell = row.locator(".cell-temp-link").first
            expect(temp_cell).to_be_visible()
            expect(temp_cell).to_contain_text("22.")

            with page.expect_response(
                lambda response: is_temperature_response_for_device(
                    response, base_url, device_id
                ),
                timeout=15_000,
            ) as response_info:
                temp_cell.click()

            expect(page).to_have_url(f"{base_url}/chart?device_ids={device_id}")
            response = response_info.value
            assert response.ok
            payload = response.json()
            assert len(payload["series"]) == 1
            series = payload["series"][0]
            assert series["device_id"] == device_id
            assert len(series["data"]) == 10
        finally:
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
