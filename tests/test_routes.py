#!/usr/bin/env python3
"""
Simple test to check if Flask routes are working
"""
# pylint: disable=unused-import
from unittest.mock import patch

from conftest import flask_test_client  # noqa: F401
from app.routes_web import _filter_speed_control_devices, _get_hubitat_sensors
from app import room_config

def test_status_endpoint(flask_test_client): # noqa: F811
    response = flask_test_client.get("/api/v1/status")
    assert response.status_code == 200


def test_logs_today_route(flask_test_client):  # noqa: F811
    """Test the /logs_today route"""
    response = flask_test_client.get("/logs_today")
    assert response.status_code == 200
    assert b"logs_today" in response.data or b"Today" in response.data


def test_all_devices_route(flask_test_client):  # noqa: F811
    """Test the /all_devices route"""
    response = flask_test_client.get("/all_devices")
    assert response.status_code == 200
    assert b"all_devices" in response.data or b"devices" in response.data


def test_about_route(flask_test_client):  # noqa: F811
    """Test the /about route"""
    response = flask_test_client.get("/about")
    assert response.status_code == 200
    assert b"About" in response.data


def test_footer_only_on_about(flask_test_client):  # noqa: F811
    """Footer should appear on About page but not on the main dashboard."""
    # About page should contain the site footer
    about_response = flask_test_client.get("/about")
    assert about_response.status_code == 200
    assert b"BasisTech LLC" in about_response.data

    # Main page should not contain the footer text anymore
    index_response = flask_test_client.get("/")
    assert index_response.status_code == 200
    assert b"BasisTech LLC" not in index_response.data


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
            "has_speed_control": True,
            "temp10x": 220,
            "calculated_temp10x": 235,
            "status": {"Mode": "COOL"},
        }
    ]

    response = flask_test_client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    assert "FCU Temp" in html
    assert "Room Temp" in html
    assert 'id="fcu-temp-12"' in html
    assert 'id="room-temp-12"' in html


@patch("app.routes_web.hubitat.get_name_to_label", return_value={})
@patch("app.routes_web.db.get_device_status")
def test_fcu_matrix_room_temp_cell_opens_weight_popup(
    mock_get_status, _mock_labels, flask_test_client
):  # noqa: F811
    """Room Temp cells must expose the source-weight popup contract."""
    mock_get_status.return_value = [
        {
            "device_id": 12,
            "device_name": "Area 51",
            "has_speed_control": True,
            "temp10x": 220,
            "calculated_temp10x": 235,
            "temp_source_stale_seconds": 600,
            "status": {"Mode": "COOL"},
        }
    ]

    response = flask_test_client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    assert 'id="fcu-temp-sources-popup"' in html
    assert (
        'data-fcu-temp-sources-url="/api/v1/fcu_temp_sources?fcu_device_id=12"'
        in html
    )
    assert 'data-fcu-temp-source-update-url="/api/v1/fcu_temp_source"' in html
    assert "Readings older than 10 minutes are ignored" in html


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


def test_hickory_route(flask_test_client):  # noqa: F811
    """Test the /hickory route"""
    response = flask_test_client.get("/hickory")
    assert response.status_code == 200
    assert b"Hickory" in response.data or b"room_dashboard" in response.data


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


def test_room_config_erv_names_start_with_erv():
    """ERV device names must start with 'ERV' — the template uses device_type
    to decide whether to show set-temp controls (fans only, not ERVs)."""
    for room_key, config in room_config.ROOM_CONFIGS.items():
        for name in config.ervs:
            assert name.startswith("ERV"), (
                f"{room_key} ERV device '{name}' must start with 'ERV'"
            )


# -- Room dashboard HTML rendering tests --


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
