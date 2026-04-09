#!/usr/bin/env python3
"""
Simple test to check if Flask routes are working
"""
# pylint: disable=unused-import
from unittest.mock import patch

from conftest import flask_test_client  # noqa: F401
from app.routes_web import _get_hubitat_sensors

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
    assert b"Local Weather" in response.data or b"AQI" in response.data


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
    assert b"elevated" in html
    assert b"problem" in html


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
