#!/usr/bin/env python3
"""
Simple test to check if Flask routes are working
"""
# pylint: disable=unused-import
from conftest import flask_test_client  # noqa: F401

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
    """Test the /air-quality route"""
    response = flask_test_client.get("/air-quality")
    assert response.status_code == 200
    assert b"Air Quality" in response.data or b"AQI" in response.data
