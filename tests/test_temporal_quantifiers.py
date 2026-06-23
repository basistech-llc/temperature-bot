"""
Test temporal quantifiers for logs and device_log endpoints
"""

import time
import os
import pytest

from app import db


def test_logs_endpoint_with_start(flask_test_client):  # noqa: F811
    """Test /api/v1/logs with start parameter"""
    start_time = int(time.time()) - 86400  # 24 hours ago
    response = flask_test_client.get(f"/api/v1/logs?start={start_time}")
    assert response.status_code == 200
    data = response.json
    assert "data" in data
    assert "recordsTotal" in data


def test_logs_endpoint_with_end(flask_test_client):  # noqa: F811
    """Test /api/v1/logs with end parameter"""
    end_time = int(time.time())
    response = flask_test_client.get(f"/api/v1/logs?end={end_time}")
    assert response.status_code == 200
    data = response.json
    assert "data" in data
    assert "recordsTotal" in data


def test_logs_endpoint_with_start_and_end(flask_test_client):  # noqa: F811
    """Test /api/v1/logs with both start and end parameters"""
    start_time = int(time.time()) - 86400  # 24 hours ago
    end_time = int(time.time())
    response = flask_test_client.get(f"/api/v1/logs?start={start_time}&end={end_time}")
    assert response.status_code == 200
    data = response.json
    assert "data" in data
    assert "recordsTotal" in data


def test_device_log_endpoint_with_start(flask_test_client):  # noqa: F811
    """Test /device_log/{device_id} with start parameter"""
    # Create a test device
    test_conn = db.connect_db(os.environ["TEST_DB_NAME"])
    cursor = test_conn.cursor()
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Test Device",))
    device_id = cursor.lastrowid
    test_conn.commit()
    test_conn.close()

    start_time = int(time.time()) - 86400  # 24 hours ago
    response = flask_test_client.get(f"/device_log/{device_id}?start={start_time}")
    assert response.status_code == 200
    assert "Test Device" in response.data.decode("utf-8")


def test_device_log_endpoint_with_end(flask_test_client):  # noqa: F811
    """Test /device_log/{device_id} with end parameter"""

    # Create a test device
    test_conn = db.connect_db(os.environ["TEST_DB_NAME"])
    cursor = test_conn.cursor()
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Test Device 2",))
    device_id = cursor.lastrowid
    test_conn.commit()
    test_conn.close()

    end_time = int(time.time())
    response = flask_test_client.get(f"/device_log/{device_id}?end={end_time}")
    assert response.status_code == 200
    assert "Test Device 2" in response.data.decode("utf-8")


def test_device_log_endpoint_with_start_and_end(flask_test_client):  # noqa: F811
    """Test /device_log/{device_id} with both start and end parameters"""
    # Create a test device
    test_conn = db.connect_db(os.environ["TEST_DB_NAME"])
    cursor = test_conn.cursor()
    cursor.execute("INSERT INTO devices (device_name) VALUES (?)", ("Test Device 3",))
    device_id = cursor.lastrowid
    test_conn.commit()
    test_conn.close()

    start_time = int(time.time()) - 86400  # 24 hours ago
    end_time = int(time.time())
    response = flask_test_client.get(
        f"/device_log/{device_id}?start={start_time}&end={end_time}"
    )
    assert response.status_code == 200
    assert "Test Device 3" in response.data.decode("utf-8")


@pytest.fixture
def test_temporal_links_in_template(flask_test_client):  # noqa: F811
    """Test that temporal links are generated correctly in the template"""
    device_id = 0
    response = flask_test_client.get("/")
    assert response.status_code == 200
    content = response.data.decode("utf-8")
    # Check that the device name and temporal links are present
    assert "Fixture Device" in content
    assert "day" in content
    assert "week" in content
    assert "all" in content
    # Check that the links have the correct format
    assert f"/device_log/{device_id}?start=" in content
    assert f"/device_log/{device_id}?start=" in content
    assert f'/device_log/{device_id}" target="_blank">all' in content


def test_temperature_api_with_device_id(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    """Test /api/v1/temperature with device_id parameter"""
    device_id = test_database_conn_with_test_data[1]
    response = flask_test_client.get(f"/api/v1/temperature?device_id={device_id}")
    assert response.status_code == 200
    data = response.json
    assert "series" in data
    # Should return data for the specific device


def test_temperature_api_with_start_and_end(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    """Test /api/v1/temperature with start and end parameters"""
    device_id = test_database_conn_with_test_data[1]
    start_time = int(time.time()) - 86400  # 24 hours ago
    end_time = int(time.time())
    response = flask_test_client.get(
        f"/api/v1/temperature?device_id={device_id}&start={start_time}&end={end_time}"
    )
    assert response.status_code == 200
    data = response.json
    assert "series" in data


def test_temperature_api_record_counts_for_temporal_ranges(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    """Temperature API returns correct datapoint counts for day/week/month/all (replaces Playwright temporal test)."""
    _, device_id, expected_counts = test_database_conn_with_test_data
    now = int(time.time())
    day_sec = 24 * 3600
    week_sec = 7 * 86400
    month_sec = 30 * 86400

    for range_name, start_delta, end_delta in [
        ("day", day_sec, 0),
        ("week", week_sec, 0),
        ("month", month_sec, 0),
    ]:
        start_ts = now - start_delta
        end_ts = now - end_delta
        response = flask_test_client.get(
            f"/api/v1/temperature?device_id={device_id}&start={start_ts}&end={end_ts}"
        )
        assert response.status_code == 200, range_name
        data = response.json
        total = sum(len(s["data"]) for s in data["series"])
        assert total == expected_counts[range_name], (
            f"range={range_name} expected={expected_counts[range_name]} got={total}"
        )

    response = flask_test_client.get(f"/api/v1/temperature?device_id={device_id}")
    assert response.status_code == 200
    data = response.json
    total = sum(len(s["data"]) for s in data["series"])
    assert total == expected_counts["all"], (
        f"range=all expected={expected_counts['all']} got={total}"
    )


def test_chart_page_with_device_id(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    """Test /chart (temperature_chart) page with device_id parameter"""
    device_id = test_database_conn_with_test_data[1]
    response = flask_test_client.get(f"/chart?device_id={device_id}")
    assert response.status_code == 200
    content = response.data.decode("utf-8")
    assert "Temperature Time Series" in content
    assert "day" in content
    assert "week" in content
    assert "month" in content


def test_index_layout_and_sections(flask_test_client):  # noqa: F811
    """Index page should show split ERV/FCU sections and Air Quality."""
    response = flask_test_client.get("/")
    assert response.status_code == 200
    content = response.data.decode("utf-8")
    # ERV and FCU sections should be clearly labeled, but allow minor wording changes.
    assert "Energy Recovery Ventilation" in content
    assert ("Fan Control Units" in content) or ("(FCUs)" in content)
    assert "Air Quality" in content


def test_index_page_has_title_and_main_grid(flask_test_client):  # noqa: F811
    """Index page has correct title and main grid container (replaces Playwright page-load check)."""
    response = flask_test_client.get("/")
    assert response.status_code == 200
    content = response.data.decode("utf-8")
    assert "Unit Speed Control" in content
    assert 'id="main-grid"' in content


def test_index_fcu_speeds_exclude_one(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    """FCU rows expose Off, Auto, 2/3/4 speeds but not 1."""
    _, device_id, _ = test_database_conn_with_test_data
    response = flask_test_client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    # Off and Auto should be present
    assert f'id="radio-{device_id}-0"' in html
    assert f'id="radio-{device_id}-auto"' in html
    assert '<th class="column-mode" rowspan="2">Mode</th>' in html
    assert '<th class="column-temp column-temp-set" rowspan="2">FCU Set Temp' in html
    assert 'class="mode-select"' in html
    assert f'id="mode-{device_id}"' in html
    assert f'id="autosettemp-widget-{device_id}"' in html
    assert 'aria-label="Auto heat and cool set temperatures"' in html
    assert 'role="group"' in html
    assert '<option value="FAN"' in html
    assert '<option value="COOL" selected>Cool</option>' in html
    assert '<option value="DRY"' in html
    assert '<option value="HEAT"' in html
    assert '<option value="AUTO"' in html

    # Speeds 2, 3, 4 should be present
    for speed in (2, 3, 4):
        assert f'id="radio-{device_id}-{speed}"' in html

    # Speed 1 should not be present for this FCU
    assert f'id="radio-{device_id}-1"' not in html


def test_index_fcu_mode_labels_lc_auto_as_auto(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    """Reported LC_AUTO should keep its raw option value but display as Auto."""
    conn, device_id, _ = test_database_conn_with_test_data
    now = int(time.time())
    conn.execute(
        """
        INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            device_id,
            now,
            60,
            240,
            (
                '{"Drive": "ON", "FanSpeed": "LOW", "Mode": "LC_AUTO", '
                '"InletTemp": "24.0", "SetTemp": "24"}'
            ),
        ),
    )
    conn.commit()

    response = flask_test_client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert '<option value="LC_AUTO" selected disabled>Auto</option>' in html
    assert '<option value="LC_AUTO" selected disabled>LC_AUTO</option>' not in html
