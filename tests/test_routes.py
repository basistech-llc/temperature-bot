#!/usr/bin/env python3
"""
Simple test to check if Flask routes are working
"""
# pylint: disable=unused-import
import datetime
from html import unescape
from unittest.mock import patch

from conftest import flask_test_client  # noqa: F401
from app.main import APP_DIR, application_metadata
from app.routes_web import (
    _dashboard_air_quality_device_is_active,
    _dashboard_device_label,
    _dashboard_device_tooltip,
    _filter_speed_control_devices,
    _get_hubitat_sensors,
    _table_update_summary,
)
from app import room_config
from app.version import __version__

def test_status_endpoint(flask_test_client): # noqa: F811
    response = flask_test_client.get("/api/v1/status")
    assert response.status_code == 200


def test_logs_today_route(flask_test_client):  # noqa: F811
    """Test the /logs_today route"""
    response = flask_test_client.get("/logs_today")
    assert response.status_code == 200
    assert b"Activity Log" in response.data


def test_all_devices_route(flask_test_client):  # noqa: F811
    """Test the /all_devices route"""
    response = flask_test_client.get("/all_devices")
    assert response.status_code == 200
    assert b"Raw Device Details" in response.data


def test_deep_dive_labels_are_descriptive(flask_test_client):  # noqa: F811
    response = flask_test_client.get("/about")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Lighting Chart" in html
    assert "Edit Devices" in html
    assert "Activity Log" in html
    assert "Raw Device Details" in html


def test_about_route(flask_test_client):  # noqa: F811
    """Test the /about route"""
    response = flask_test_client.get("/about")
    assert response.status_code == 200
    assert b"About" in response.data


def test_footer_metadata_on_all_pages(flask_test_client):  # noqa: F811
    """Footer metadata should appear on every rendered page."""
    for path in ("/", "/about"):
        response = flask_test_client.get(path)
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        metadata = application_metadata()
        assert f"© {metadata.deployment_year} BasisTech." in html
        assert "BasisTech LLC" not in html
        assert f"Version {__version__}." in html
        assert "Deployed " in html
        assert (
            f'Git <a href="{metadata.git_branch_url}">{metadata.git_commit}</a>.'
            in html
        )


def test_application_metadata_uses_app_directory_mtime():
    """Deployment date should come from the app directory mtime."""
    application_metadata.cache_clear()
    expected_deployment_date = datetime.datetime.fromtimestamp(
        APP_DIR.stat().st_mtime
    ).strftime("%Y-%m-%d %H:%M:%S")
    expected_deployment_year = datetime.datetime.fromtimestamp(
        APP_DIR.stat().st_mtime
    ).year
    metadata = application_metadata()

    assert metadata.app_version == __version__
    assert metadata.deployment_date == expected_deployment_date
    assert metadata.deployment_year == expected_deployment_year
    assert str(metadata.git_branch_url).startswith(
        "https://github.com/basistech-llc/temperature-bot/tree/"
    )
    assert metadata.git_commit


def test_simulator_banner_is_rendered(flask_test_client):  # noqa: F811
    response = flask_test_client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert 'class="simulator-banner"' in html
    assert ">simulator</div>" in html


def test_rooms_menu_has_one_plain_link_per_room(flask_test_client):  # noqa: F811
    """Rooms menu should not duplicate embedded/no-return variants."""
    response = flask_test_client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert html.count('href="/hickory"') == 1
    assert html.count('href="/kitchen"') == 1
    assert "/hickory?embedded" not in html
    assert "/kitchen?embedded" not in html
    assert "no-return" not in html


def test_dashboard_device_label_uses_stored_status_label():
    """Index labels must not require a live Hubitat fetch."""
    label = _dashboard_device_label(
        {
            "device_name": "Lobby Sensor on Somerville Broadway",
            "status": {"label": "Lobby Sensor"},
        }
    )

    assert label == "Lobby Sensor"


def test_dashboard_device_tooltip_uses_device_update_time():
    tooltip = _dashboard_device_tooltip(
        {
            "device_name": "Area 51",
            "logtime": 1000,
            "duration": 60,
        },
        now=1300,
    )

    assert tooltip.startswith("Area 51\nLast updated at ")
    assert tooltip.endswith(" - 4m ago")


def test_dashboard_air_quality_device_expires_after_30_days():
    current_device = {
        "has_speed_control": False,
        "temp10x": 220,
        "logtime": 1000,
        "duration": 60,
    }
    expired_device = {
        "has_speed_control": False,
        "temp10x": 220,
        "logtime": 1000,
        "duration": 60,
    }

    assert _dashboard_air_quality_device_is_active(current_device, now=1300)
    assert not _dashboard_air_quality_device_is_active(
        expired_device,
        now=1000 + 60 + 31 * 24 * 60 * 60,
    )
    assert not _dashboard_air_quality_device_is_active(
        {**current_device, "has_speed_control": True},
        now=1300,
    )


@patch("app.routes_web.hubitat.get_name_to_label")
@patch("app.routes_web.time.time", return_value=1300)
@patch("app.routes_web.db.get_device_status")
def test_index_does_not_fetch_hubitat_labels_on_render(
    mock_get_status, _mock_time, mock_get_name_to_label, flask_test_client
):  # noqa: F811
    mock_get_status.return_value = [
        {
            "device_id": 12,
            "device_name": "Lobby Sensor on Somerville Broadway",
            "has_speed_control": False,
            "temp10x": 220,
            "logtime": 1000,
            "duration": 1,
            "status": {"label": "Lobby Sensor", "humidity": 40},
        }
    ]

    response = flask_test_client.get("/")
    assert response.status_code == 200
    assert "Lobby Sensor" in response.data.decode("utf-8")
    mock_get_name_to_label.assert_not_called()


def test_table_update_summary_uses_oldest_status_end_time():
    summary = _table_update_summary(
        [
            {"device_type": "ERV", "logtime": 900, "duration": 1},
            {
                "device_name": "Older FCU",
                "device_type": "FCU",
                "logtime": 1000,
                "duration": 60,
            },
            {
                "device_name": "Newer FCU",
                "device_type": "FCU",
                "logtime": 1100,
                "duration": 20,
            },
            {"device_type": "FCU", "duration": 20},
            {
                "device_name": "Newest FCU",
                "device_type": "FCU",
                "logtime": 1200,
                "duration": 0,
            },
        ],
        lambda device: device.get("device_type") == "FCU",
        now=1300,
    )

    assert summary is not None
    assert summary.oldest_update_at == 1060
    assert summary.oldest_update_age == "4m"
    assert summary.source_device_name == "Older FCU"
    assert summary.label == (
        f"(oldest update at {summary.oldest_update_datetime} - "
        "4m ago from Older FCU)"
    )


@patch("app.routes_web.hubitat.get_name_to_label", return_value={})
@patch("app.routes_web.time.time", return_value=1300)
@patch("app.routes_web.db.get_device_status")
def test_index_table_update_summaries_render_at_table_bottom(
    mock_get_status, _mock_time, _mock_labels, flask_test_client
):  # noqa: F811
    mock_get_status.return_value = [
        {
            "device_id": 10,
            "device_name": "ERV Test",
            "device_type": "ERV",
            "has_speed_control": True,
            "temp10x": 210,
            "logtime": 1000,
            "duration": 1,
        },
        {
            "device_id": 11,
            "device_name": "FCU Test",
            "device_type": "FCU",
            "has_speed_control": True,
            "temp10x": 220,
            "calculated_temp10x": 221,
            "logtime": 1010,
            "duration": 1,
            "status": {"Mode": "COOL"},
        },
        {
            "device_id": 12,
            "device_name": "Air Test",
            "has_speed_control": False,
            "temp10x": 230,
            "logtime": 1020,
            "duration": 1,
            "status": {"humidity": 40},
        },
    ]

    response = flask_test_client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    assert 'id="oldest-update-erv"' in html
    assert 'id="oldest-update-fcu"' in html
    assert 'id="oldest-update-air-quality"' in html
    assert html.count("oldest update at") == 3


@patch("app.routes_web.hubitat.get_name_to_label", return_value={})
@patch("app.routes_web.time.time", return_value=1300)
@patch("app.routes_web.db.get_device_status")
def test_index_air_quality_table_hides_expired_devices(
    mock_get_status, _mock_time, _mock_labels, flask_test_client
):  # noqa: F811
    mock_get_status.return_value = [
        {
            "device_id": 12,
            "device_name": "Current Air",
            "has_speed_control": False,
            "temp10x": 230,
            "logtime": 1020,
            "duration": 1,
            "status": {"humidity": 40},
        },
        {
            "device_id": 13,
            "device_name": "Expired Air",
            "has_speed_control": False,
            "temp10x": 240,
            "logtime": 1000 - 31 * 24 * 60 * 60,
            "duration": 1,
            "status": {"humidity": 40},
        },
    ]

    response = flask_test_client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    assert "Current Air" in html
    assert "Expired Air" not in html
    assert "from Current Air" in html
    assert "from Expired Air" not in html


@patch("app.routes_web.hubitat.get_name_to_label", return_value={})
@patch("app.routes_web.db.get_device_status")
def test_fcu_matrix_has_raw_fcu_temp_and_room_temp_columns(
    mock_get_status, _mock_labels, flask_test_client
):  # noqa: F811
    """The FCU matrix must display raw FCU temperature and calculated room temperature."""
    mock_get_status.return_value = [
        {
            "device_id": 12,
            "device_name": "Area 51",
            "device_type": "FCU",
            "has_speed_control": True,
            "temp10x": 220,
            "calculated_temp10x": 235,
            "status": {"Mode": "COOL"},
        }
    ]

    response = flask_test_client.get("/")
    assert response.status_code == 200
    html = unescape(response.data.decode("utf-8"))

    assert "Room (Unit)" in html
    assert "FCU Temp" in html
    assert "Computed Room" in html
    assert "column-computed-room-temp" in html
    assert 'id="fcu-room-temp-unit-label"' in html
    assert 'class="column-room-humidity"' in html
    assert "Rule Set Range" in html
    assert 'id="fcu-temp-12"' in html
    assert "cell-fcu-temp" in html
    assert 'data-chart-url="/chart?mode=raw&device_ids=12"' in html
    assert "FCU temperature chart for Area 51; click to show graph." in html
    assert 'id="room-temp-12"' in html
    assert "cell-room-temp" in html
    assert "cell-room-humidity" in html
    assert 'data-chart-url="/chart?mode=calculated&device_ids=12"' in html
    assert "Calculated room temperature chart for Area 51; click to show graph." in html
    assert 'data-update-url="/api/v1/set_auto_temp"' in html
    assert 'aria-label="Move Auto heat set temperature"' in html
    assert 'aria-label="Move Auto cool set temperature"' in html


@patch("app.routes_web.hubitat.get_name_to_label", return_value={})
@patch("app.routes_web.db.get_device_status")
def test_fcu_matrix_room_unit_cell_opens_room_editor(
    mock_get_status, _mock_labels, flask_test_client
):  # noqa: F811
    """Room (Unit) cells must expose the editor/source-weight popup contract."""
    mock_get_status.return_value = [
        {
            "device_id": 12,
            "device_name": "Area 51",
            "device_type": "FCU",
            "has_speed_control": True,
            "temp10x": 220,
            "calculated_temp10x": 235,
            "temp_source_stale_seconds": 600,
            "room_name": "Area 51",
            "status": {"Mode": "COOL"},
        }
    ]

    response = flask_test_client.get("/")
    assert response.status_code == 200
    html = unescape(response.data.decode("utf-8"))

    assert 'id="fcu-temp-sources-popup"' in html
    assert 'class="device-name-context fcu-room-editor-trigger"' in html
    assert 'role="button"' in html
    assert 'tabindex="0"' in html
    assert 'data-device-update-url="/api/v1/devices/12"' in html
    assert (
        'data-fcu-temp-sources-url="/api/v1/fcu_temp_sources?fcu_device_id=12"'
        in html
    )
    assert 'data-fcu-temp-source-update-url="/api/v1/fcu_temp_source"' in html
    assert 'data-fcu-temp-sources-room-name="Area 51"' in html
    assert 'id="fcu-room-display-name"' in html
    assert "Room (Unit) name" in html
    assert "Readings older than 10 minutes are ignored" in html
    assert 'data-action="save-fcu-temp-sources"' in html
    assert 'data-action="revert-fcu-temp-sources"' in html
    assert 'data-action="cancel-fcu-temp-sources"' in html
    assert 'data-action="close-fcu-temp-sources"' not in html
    assert "room-temp-link" not in html


@patch("app.routes_web.hubitat.get_name_to_label", return_value={})
@patch("app.routes_web.time.time", return_value=1300)
@patch("app.routes_web.db.get_device_status")
def test_index_device_names_expose_rename_popup_contract(
    mock_get_status, _mock_time, _mock_labels, flask_test_client
):  # noqa: F811
    mock_get_status.return_value = [
        {
            "device_id": 12,
            "device_name": "Area 51",
            "display_name": "Server Room",
            "device_type": "FCU",
            "rules_enabled": False,
            "has_speed_control": True,
            "temp10x": 220,
            "calculated_temp10x": 235,
            "logtime": 1000,
            "duration": 60,
            "status": {"Mode": "COOL"},
        }
    ]

    response = flask_test_client.get("/")
    assert response.status_code == 200
    html = unescape(response.data.decode("utf-8"))

    assert 'class="device-name-context fcu-room-editor-trigger"' in html
    assert 'data-device-id="12"' in html
    assert 'data-device-name="Area 51"' in html
    assert 'data-display-name="Server Room"' in html
    assert 'data-device-type="FCU"' in html
    assert 'data-rules-enabled="false"' in html
    assert 'data-device-update="' in html
    assert " - 4m ago" in html
    assert 'id="device-rename-popup"' in html
    assert 'id="device-rename-device-type"' in html
    assert 'id="device-rename-rules-enabled"' in html
    assert 'id="device-rename-last-update"' in html
    assert 'data-action="reset-device-name"' in html
    assert 'data-action="rename-device"' in html
    assert 'data-action="cancel-device-rename"' in html


def test_temperature_chart_page_has_raw_calculated_mode_switch(
    flask_test_client,
):  # noqa: F811
    """The chart page must let users switch between raw and calculated temperatures."""
    response = flask_test_client.get("/chart")
    assert response.status_code == 200
    html = response.data.decode("utf-8").lower()

    assert "raw temps" in html
    assert "calculated temps" in html
    assert 'name="temperature-mode"' in html


def test_privacy_route(flask_test_client):  # noqa: F811
    """Test the /privacy route redirects to /about"""
    response = flask_test_client.get("/privacy", follow_redirects=False)
    assert response.status_code == 302
    assert response.location.endswith("/about")


def test_terms_route(flask_test_client):  # noqa: F811
    """Test the /terms route redirects to /about"""
    response = flask_test_client.get("/terms", follow_redirects=False)
    assert response.status_code == 302
    assert response.location.endswith("/about")


def test_kitchen_route(flask_test_client):  # noqa: F811
    """Test the /kitchen route"""
    response = flask_test_client.get("/kitchen")
    assert response.status_code == 200
    assert b"Kitchen" in response.data or b"room_dashboard" in response.data
    assert b"/static/hickory_life.js" not in response.data


def test_hickory_route(flask_test_client):  # noqa: F811
    """Test the /hickory route"""
    response = flask_test_client.get("/hickory")
    assert response.status_code == 200
    assert b"Hickory" in response.data or b"room_dashboard" in response.data
    assert b"/static/hickory_life.js" in response.data


def test_weather_route(flask_test_client):  # noqa: F811
    """Test the /weather route"""
    response = flask_test_client.get("/weather")
    assert response.status_code == 200
    assert b"Current Conditions" in response.data
    assert b"Forecast for CALA" in response.data
    assert b"Outdoor Air Quality" in response.data


def test_air_quality_route(flask_test_client):  # noqa: F811
    """Test the /air-quality route structure and key content."""
    response = flask_test_client.get("/air-quality")
    assert response.status_code == 200

    html = response.data

    # Section headings
    assert b"Indoor Air Quality" in html
    assert b"Outdoor Air Quality" in html

    # Column headings
    for heading in [b"CO2", b"Humidity", b"PM1", b"PM2.5", b"Pressure", b"Radon", b"Temp", b"VOC"]:
        assert heading in html

    # Legend and explanatory text
    assert b"Shading:" in html
    assert b"air_quality_coloring.js" in html
    assert b"good" in html
    assert b"fair" in html
    assert b"poor" in html


def test_air_quality_cells_are_clickable(flask_test_client):  # noqa: F811
    """Each indoor AQ metric cell must carry a chart-url so clickable_cells.js opens the chart.

    Guards against a regression where the shared click handler is still loaded but the
    template stops emitting the data-chart-url attribute (or the URL format diverges
    from /metric_chart's expected querystring). Uses a synthetic airmon row because
    the test DB does not ship Airthings sample data.
    """
    synthetic_row = {
        "device_id": 99,
        "device_name": "Airthings Test",
        "display_name": "Test Room",
        "logtime": 1000,
        "status": {
            "co2": {"value": 600, "unit": "ppm"},
            "humidity": {"value": 45, "unit": "%"},
            "voc": {"value": 100, "unit": "ppb"},
            "radonShortTermAvg": {"value": 25, "unit": "Bq/m3"},
            "pm25": {"value": 3, "unit": "ug/m3"},
            "pm1": {"value": 2, "unit": "ug/m3"},
            "pressure": {"value": 1013, "unit": "hPa"},
            "temp": {"value": 21.5, "unit": "degC"},
        },
    }

    with patch("app.db.get_all_device_aqi", return_value=[synthetic_row]):
        response = flask_test_client.get("/air-quality")

    assert response.status_code == 200
    html = response.data.decode("utf-8")

    # Every metric with a dedicated chart page must be linked from its cell.
    for metric in ("co2", "humidity", "voc", "radon", "pm25", "pm1", "pressure"):
        assert f"/metric_chart?metric={metric}&device_ids=99" in html, metric
    # Temperature uses the existing /chart route, not /metric_chart.
    assert "/chart?device_ids=99" in html
    # The shared click handler is loaded via base.html.
    assert "clickable_cells.js" in html
    assert 'data-air-quality-metric="co2"' in html
    assert 'data-air-quality-metric="humidity"' in html


# -- _filter_speed_control_devices unit tests --

_FAKE_SPEED_DEVICES = [
    {"device_name": "Area 51", "has_speed_control": True},
    {"device_name": "Restrooms/BOH", "has_speed_control": True},
    {"device_name": "ERV Kitchen", "has_speed_control": True},
    {"device_name": "Dungeon", "has_speed_control": False},
    {"device_name": "Lobby Sensor", "has_speed_control": False},
]


def test_filter_speed_control_returns_all_matches():
    """All devices whose names appear in the filter list AND have speed control
    must be returned — not just the first match.

    Prevents regression of the old [filtered[0]] bug that suppressed
    all but one FCU per room.
    """
    result = _filter_speed_control_devices(
        _FAKE_SPEED_DEVICES, ["Area 51", "Restrooms/BOH"]
    )
    names = [d["device_name"] for d in result]
    assert names == ["Area 51", "Restrooms/BOH"]


def test_filter_speed_control_excludes_non_speed_devices():
    """Devices without has_speed_control are excluded even if name matches."""
    result = _filter_speed_control_devices(_FAKE_SPEED_DEVICES, ["Dungeon"])
    assert result == []


def test_filter_speed_control_empty_names():
    """Empty name list returns no devices."""
    result = _filter_speed_control_devices(_FAKE_SPEED_DEVICES, [])
    assert result == []


# -- _get_hubitat_sensors unit tests --

_FAKE_HUBITAT_DEVICES = [
    {
        "name": "Hickory Sensor",
        "label": "Hickory Sensor",
        "id": "582",
        "room": "Hickory",
        "capabilities": ["TemperatureMeasurement", "RelativeHumidityMeasurement"],
        "attributes": {"temperature": "23.4", "humidity": "24"},
    },
    {
        "name": "Dungeon Cage",
        "label": "Dungeon Cage",
        "id": "98",
        "room": "Dungeon",
        "capabilities": ["TemperatureMeasurement"],
        "attributes": {"temperature": "24.6"},
    },
    {
        "name": "Some Light",
        "label": "Some Light",
        "id": "999",
        "room": "Hickory",
        "capabilities": ["Switch"],
        "attributes": {"switch": "on"},
    },
]


@patch("app.routes_web.hubitat.get_all_devices", return_value=_FAKE_HUBITAT_DEVICES)
def test_get_hubitat_sensors_returns_matching(_mock):
    """Configured names found in Hubitat are returned."""
    result = _get_hubitat_sensors(["Hickory Sensor", "Dungeon Cage"])
    names = [s["name"] for s in result]
    assert names == ["Hickory Sensor", "Dungeon Cage"]
    assert all("offline" not in s for s in result)


@patch("app.routes_web.hubitat.get_all_devices", return_value=_FAKE_HUBITAT_DEVICES)
def test_get_hubitat_sensors_offline_placeholder(_mock):
    """Configured names NOT in Hubitat get an offline placeholder."""
    result = _get_hubitat_sensors(["Hickory Sensor", "Missing Sensor"])
    assert len(result) == 2
    online = result[0]
    offline = result[1]
    assert online["name"] == "Hickory Sensor"
    assert "offline" not in online
    assert offline["name"] == "Missing Sensor"
    assert offline["offline"] is True


@patch("app.routes_web.hubitat.get_all_devices", return_value=_FAKE_HUBITAT_DEVICES)
def test_get_hubitat_sensors_skips_non_temperature(_mock):
    """Devices without TemperatureMeasurement capability are not returned."""
    result = _get_hubitat_sensors(["Some Light"])
    assert len(result) == 1
    assert result[0]["offline"] is True


@patch("app.routes_web.hubitat.get_all_devices", side_effect=RuntimeError("unreachable"))
def test_get_hubitat_sensors_hubitat_unreachable(_mock):
    """When Hubitat is unreachable, all sensors get offline placeholders."""
    result = _get_hubitat_sensors(["Hickory Sensor", "Dungeon Cage"])
    assert len(result) == 2
    assert all(s["offline"] is True for s in result)


# -- Hickory room API endpoint tests --

_FAKE_ALL_DEVICES = [
    {
        "id": "581",
        "label": "Hickory Dimmer",
        "capabilities": ["SwitchLevel"],
        "attributes": {"level": 75, "switch": "on"},
    },
    {
        "id": "454",
        "label": "Wall Inner",
        "capabilities": ["Switch"],
        "attributes": {"switch": "on"},
    },
    {
        "id": "550",
        "label": "Wall Outer",
        "capabilities": ["Switch"],
        "attributes": {"switch": "off"},
    },
]


# /api/v1/hickory/room_status

@patch("app.routes_api.hubitat.get_all_devices", return_value=_FAKE_ALL_DEVICES)
def test_room_status_returns_device_states(_mock, flask_test_client):  # noqa: F811
    """Room status returns dimmer level and wall light states."""
    resp = flask_test_client.get("/api/v1/hickory/room_status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["dimmer"]["level"] == 75
    assert data["dimmer"]["switch"] == "on"
    assert data["wall_inner"]["switch"] == "on"
    assert data["wall_outer"]["switch"] == "off"


@patch("app.routes_api.hubitat.get_all_devices", return_value=[])
def test_room_status_missing_devices(_mock, flask_test_client):  # noqa: F811
    """When configured devices aren't in Hubitat, they're omitted from response."""
    resp = flask_test_client.get("/api/v1/hickory/room_status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "dimmer" not in data
    assert "wall_inner" not in data
    assert "wall_outer" not in data


@patch("app.routes_api.hubitat.get_all_devices", side_effect=RuntimeError("hub down"))
def test_room_status_hubitat_error(_mock, flask_test_client):  # noqa: F811
    """Hubitat failure returns 500."""
    resp = flask_test_client.get("/api/v1/hickory/room_status")
    assert resp.status_code == 500
    assert "error" in resp.get_json()


# /api/v1/hickory/dimmer

@patch("app.routes_api.hubitat.set_dimmer_level")
def test_dimmer_valid_level(_mock, flask_test_client):  # noqa: F811
    """Valid dimmer level returns ok."""
    resp = flask_test_client.post(
        "/api/v1/hickory/dimmer",
        json={"level": 50},
    )
    assert resp.status_code == 200
    assert resp.get_json()["level"] == 50
    _mock.assert_called_once_with("581", 50)


@patch("app.routes_api.hubitat.set_dimmer_level")
def test_dimmer_level_zero(_mock, flask_test_client):  # noqa: F811
    """Level 0 is valid (turns light off)."""
    resp = flask_test_client.post(
        "/api/v1/hickory/dimmer",
        json={"level": 0},
    )
    assert resp.status_code == 200
    _mock.assert_called_once_with("581", 0)


def test_dimmer_missing_level(flask_test_client):  # noqa: F811
    """Missing level returns 400."""
    resp = flask_test_client.post(
        "/api/v1/hickory/dimmer",
        json={},
    )
    assert resp.status_code == 400


def test_dimmer_out_of_range(flask_test_client):  # noqa: F811
    """Level outside 0-100 returns 400."""
    resp = flask_test_client.post(
        "/api/v1/hickory/dimmer",
        json={"level": 101},
    )
    assert resp.status_code == 400


def test_dimmer_non_integer(flask_test_client):  # noqa: F811
    """Non-integer level returns 400."""
    resp = flask_test_client.post(
        "/api/v1/hickory/dimmer",
        json={"level": "bright"},
    )
    assert resp.status_code == 400


@patch("app.routes_api.hubitat.set_dimmer_level", side_effect=OSError("timeout"))
def test_dimmer_hubitat_error(_mock, flask_test_client):  # noqa: F811
    """Hubitat failure returns 500."""
    resp = flask_test_client.post(
        "/api/v1/hickory/dimmer",
        json={"level": 50},
    )
    assert resp.status_code == 500
    assert "error" in resp.get_json()


# /api/v1/hickory/wall_light

@patch("app.routes_api.hubitat.set_switch")
def test_wall_light_on(_mock, flask_test_client):  # noqa: F811
    """Turning inner wall light on returns ok."""
    resp = flask_test_client.post(
        "/api/v1/hickory/wall_light",
        json={"light": "inner", "state": "on"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["light"] == "inner"
    assert data["state"] == "on"
    _mock.assert_called_once_with("454", "on")


@patch("app.routes_api.hubitat.set_switch")
def test_wall_light_outer_off(_mock, flask_test_client):  # noqa: F811
    """Turning outer wall light off returns ok."""
    resp = flask_test_client.post(
        "/api/v1/hickory/wall_light",
        json={"light": "outer", "state": "off"},
    )
    assert resp.status_code == 200
    _mock.assert_called_once_with("550", "off")


def test_wall_light_invalid_light(flask_test_client):  # noqa: F811
    """Invalid light name returns 400."""
    resp = flask_test_client.post(
        "/api/v1/hickory/wall_light",
        json={"light": "ceiling", "state": "on"},
    )
    assert resp.status_code == 400


def test_wall_light_invalid_state(flask_test_client):  # noqa: F811
    """Invalid state returns 400."""
    resp = flask_test_client.post(
        "/api/v1/hickory/wall_light",
        json={"light": "inner", "state": "toggle"},
    )
    assert resp.status_code == 400


def test_wall_light_missing_fields(flask_test_client):  # noqa: F811
    """Missing both fields returns 400."""
    resp = flask_test_client.post(
        "/api/v1/hickory/wall_light",
        json={},
    )
    assert resp.status_code == 400


@patch("app.routes_api.hubitat.set_switch", side_effect=RuntimeError("hub down"))
def test_wall_light_hubitat_error(_mock, flask_test_client):  # noqa: F811
    """Hubitat failure returns 500."""
    resp = flask_test_client.post(
        "/api/v1/hickory/wall_light",
        json={"light": "inner", "state": "on"},
    )
    assert resp.status_code == 500
    assert "error" in resp.get_json()


# /api/v1/hickory/tv

@patch("app.routes_api.hubitat.control_hickory_tv")
def test_tv_up(_mock, flask_test_client):  # noqa: F811
    """TV up returns ok."""
    resp = flask_test_client.post(
        "/api/v1/hickory/tv",
        json={"direction": "up"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["direction"] == "up"
    _mock.assert_called_once_with("up")


@patch("app.routes_api.hubitat.control_hickory_tv")
def test_tv_down(_mock, flask_test_client):  # noqa: F811
    """TV down returns ok."""
    resp = flask_test_client.post(
        "/api/v1/hickory/tv",
        json={"direction": "down"},
    )
    assert resp.status_code == 200
    _mock.assert_called_once_with("down")


def test_tv_invalid_direction(flask_test_client):  # noqa: F811
    """Invalid direction returns 400."""
    resp = flask_test_client.post(
        "/api/v1/hickory/tv",
        json={"direction": "left"},
    )
    assert resp.status_code == 400


def test_tv_missing_direction(flask_test_client):  # noqa: F811
    """Missing direction returns 400."""
    resp = flask_test_client.post(
        "/api/v1/hickory/tv",
        json={},
    )
    assert resp.status_code == 400


@patch("app.routes_api.hubitat.control_hickory_tv", side_effect=RuntimeError("not found"))
def test_tv_hubitat_error(_mock, flask_test_client):  # noqa: F811
    """Hubitat failure returns 500."""
    resp = flask_test_client.post(
        "/api/v1/hickory/tv",
        json={"direction": "up"},
    )
    assert resp.status_code == 500
    assert "error" in resp.get_json()


# -- Room config tests --


def test_room_config_kitchen_has_fcu():
    """Kitchen must list its FCU so set-temp controls render."""
    fans = room_config.ROOM_CONFIGS["kitchen"].fans
    assert "Kitchen" in fans


def test_room_config_no_erv_in_fans():
    """ERV devices must never appear in the 'fans' list.

    The template renders set-temp controls only for fan-type devices.
    If an ERV accidentally ends up in the fans list, users would see
    temperature controls that send meaningless API calls.
    """
    for room_key, config in room_config.ROOM_CONFIGS.items():
        for fan_name in config.fans:
            assert not fan_name.startswith("ERV"), (
                f"{room_key} fans list contains ERV device '{fan_name}'"
            )


@patch("app.routes_web.db.get_device_status")
def test_hickory_dashboard_uses_decluttered_layout(mock_get_status, flask_test_client):  # noqa: F811
    """Guard Carl's June 2026 room-dashboard restructure (hvac-00i).

    Carl found the page jargon-heavy and cluttered. This pins the de-jargoned,
    reordered layout so it can't silently regress:
    - the "<Location> HVAC Control" header is gone (no on-screen jargon);
    - the "Room Controls" and "Temperature Sensors" section captions are gone;
    - the Room Controls block leads the page, above the first HVAC device card.

    We inject one speed-control device matching Hickory's config so an HVAC card
    actually renders; otherwise the ordering check would be vacuous (device cards
    are DB-driven and absent from the bare test fixture).
    """
    mock_get_status.return_value = [
        {
            "device_id": 117,
            "device_name": "ERV Restrooms",  # matches room_config hickory.ervs
            "has_speed_control": True,
        }
    ]

    response = flask_test_client.get("/hickory")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    assert "HVAC Control" not in html
    assert "<h2>Room Controls</h2>" not in html
    assert "<h2>Temperature Sensors</h2>" not in html

    # Anchor on the HTML usage (class="...") rather than the bare class name,
    # which also appears earlier in the embedded <style> block. The room-controls
    # card uses class="device-card room-controls-card"; HVAC cards use the bare
    # class="device-card", so the two finds resolve to distinct elements.
    room_controls_pos = html.find('class="device-card room-controls-card"')
    first_device_card_pos = html.find('class="device-card"')
    assert room_controls_pos != -1, "Room Controls block missing"
    assert first_device_card_pos != -1, "expected the injected HVAC device card"
    assert room_controls_pos < first_device_card_pos, (
        "Room Controls must render above the first HVAC device card"
    )
