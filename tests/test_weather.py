"""
Tests for app/weather.py — WeatherService and get_weather_data.
"""

import datetime
from unittest.mock import patch, MagicMock

import requests

from app.weather import WeatherService, get_weather_data


# ── Shared NWS API response fixtures ──────────────────────────────

FAKE_POINTS = {
    "properties": {
        "observationStations": "https://api.weather.gov/gridpoints/BOX/70,91/stations",
        "forecastHourly": "https://api.weather.gov/gridpoints/BOX/70,91/forecast/hourly",
        "forecast": "https://api.weather.gov/gridpoints/BOX/70,91/forecast",
    }
}

FAKE_STATIONS = {
    "features": [
        {"properties": {"stationIdentifier": "KBOS", "name": "Boston Logan"}},
        {"properties": {"stationIdentifier": "KBED", "name": "Hanscom Field"}},
        {"properties": {"stationIdentifier": "KOWD", "name": "Norwood"}},
    ]
}

def _make_observation(temp_c, conditions, icon=""):
    return {
        "properties": {
            "temperature": {"value": temp_c, "unitCode": "wmoUnit:degC"},
            "textDescription": conditions,
            "icon": icon,
        }
    }

def _make_hourly_periods(count=5):
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    periods = []
    for i in range(count):
        start = now + datetime.timedelta(hours=i)
        end = start + datetime.timedelta(hours=1)
        periods.append({
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
            "temperature": 50 + i,
            "shortForecast": "Cloudy",
            "icon": "",
        })
    return {"properties": {"periods": periods}}

def _make_daily_periods(count=5):
    names = ["Today", "Tonight", "Monday", "Monday Night", "Tuesday"]
    return {
        "properties": {
            "periods": [
                {"name": names[i % len(names)], "temperature": 70 + i, "shortForecast": "Sunny"}
                for i in range(count)
            ]
        }
    }


# ── WeatherService.get_current_conditions ─────────────────────────

@patch("app.weather.requests.Session")
def test_get_current_conditions_returns_multiple_stations(mock_session_cls):
    """get_current_conditions returns a list with one entry per station."""
    session = MagicMock()
    mock_session_cls.return_value = session

    session.get.return_value.json.side_effect = [
        FAKE_POINTS,
        FAKE_STATIONS,
        _make_observation(10.0, "Cloudy"),
        _make_observation(8.5, "Clear"),
    ]
    session.get.return_value.raise_for_status = MagicMock()

    svc = WeatherService(latitude=42.38, longitude=-71.10)
    result = svc.get_current_conditions(num_stations=2)

    assert len(result) == 2
    assert result[0]["station_name"] == "Boston Logan"
    assert result[0]["temperature"] == 10.0
    assert result[0]["conditions"] == "Cloudy"
    assert result[1]["station_name"] == "Hanscom Field"
    assert result[1]["temperature"] == 8.5


@patch("app.weather.requests.Session")
def test_get_current_conditions_empty_stations(mock_session_cls):
    """Returns empty list when no stations available."""
    session = MagicMock()
    mock_session_cls.return_value = session

    session.get.return_value.json.side_effect = [
        FAKE_POINTS,
        {"features": []},
    ]
    session.get.return_value.raise_for_status = MagicMock()

    svc = WeatherService(latitude=42.38, longitude=-71.10)
    result = svc.get_current_conditions()

    assert not result


@patch("app.weather.requests.Session")
def test_get_current_conditions_skips_failing_station(mock_session_cls):
    """If one station observation fails, the other still returns."""
    session = MagicMock()
    mock_session_cls.return_value = session

    obs_ok = MagicMock()
    obs_ok.json.return_value = _make_observation(9.0, "Rain")
    obs_ok.raise_for_status = MagicMock()

    obs_fail = MagicMock()
    obs_fail.raise_for_status.side_effect = requests.exceptions.RequestException("timeout")

    # points → stations → fail → succeed
    points_resp = MagicMock()
    points_resp.json.return_value = FAKE_POINTS
    points_resp.raise_for_status = MagicMock()

    stations_resp = MagicMock()
    stations_resp.json.return_value = FAKE_STATIONS
    stations_resp.raise_for_status = MagicMock()

    session.get.side_effect = [points_resp, stations_resp, obs_fail, obs_ok]

    svc = WeatherService(latitude=42.38, longitude=-71.10)
    result = svc.get_current_conditions(num_stations=2)

    assert len(result) == 1
    assert result[0]["station_name"] == "Hanscom Field"


# ── WeatherService.get_forecast ───────────────────────────────────

@patch("app.weather.requests.Session")
def test_get_forecast_returns_five_periods(mock_session_cls):
    """get_forecast returns up to 5 hourly periods."""
    session = MagicMock()
    mock_session_cls.return_value = session

    session.get.return_value.json.side_effect = [
        FAKE_POINTS,
        _make_hourly_periods(8),
    ]
    session.get.return_value.raise_for_status = MagicMock()

    svc = WeatherService(latitude=42.38, longitude=-71.10)
    result = svc.get_forecast()

    assert len(result) == 5
    assert "time" in result[0]
    assert "temperature" in result[0]
    assert "conditions" in result[0]


# ── WeatherService.get_daily_forecast ─────────────────────────────

@patch("app.weather.requests.Session")
def test_get_daily_forecast_returns_named_periods(mock_session_cls):
    """get_daily_forecast returns named day/night periods."""
    session = MagicMock()
    mock_session_cls.return_value = session

    session.get.return_value.json.side_effect = [
        FAKE_POINTS,
        _make_daily_periods(6),
    ]
    session.get.return_value.raise_for_status = MagicMock()

    svc = WeatherService(latitude=42.38, longitude=-71.10)
    result = svc.get_daily_forecast(num_periods=5)

    assert len(result) == 5
    assert result[0]["name"] == "Today"
    assert "temperature" in result[0]
    assert "conditions" in result[0]


# ── WeatherService.get_all_weather_data ───────────────────────────

@patch("app.weather.requests.Session")
def test_get_all_weather_data_shape(mock_session_cls):
    """get_all_weather_data returns dict with stations, forecast, daily keys."""
    session = MagicMock()
    mock_session_cls.return_value = session

    session.get.return_value.json.side_effect = [
        FAKE_POINTS,
        FAKE_STATIONS,
        _make_observation(10.0, "Cloudy"),
        _make_observation(8.0, "Cloudy"),
        _make_hourly_periods(5),
        _make_daily_periods(5),
    ]
    session.get.return_value.raise_for_status = MagicMock()

    svc = WeatherService(latitude=42.38, longitude=-71.10)
    result = svc.get_all_weather_data()

    assert "stations" in result
    assert "forecast" in result
    assert "daily" in result
    assert isinstance(result["stations"], list)
    assert isinstance(result["forecast"], list)
    assert isinstance(result["daily"], list)


# ── get_weather_data (module-level wrapper) ───────────────────────

@patch("app.weather.WeatherService")
def test_get_weather_data_success(mock_svc_cls):
    """get_weather_data returns data from WeatherService."""
    mock_svc = MagicMock()
    mock_svc.get_all_weather_data.return_value = {
        "stations": [{"temperature": 10, "conditions": "Clear",
                       "icon": "", "station_name": "Test"}],
        "forecast": [],
        "daily": [],
    }
    mock_svc_cls.return_value = mock_svc

    result = get_weather_data(latitude=42.0, longitude=-71.0)

    assert "stations" in result
    assert result["stations"][0]["temperature"] == 10
    mock_svc.close.assert_called_once()


@patch("app.weather.WeatherService")
def test_get_weather_data_connection_error(mock_svc_cls):
    """get_weather_data returns error dict on ConnectionError."""
    mock_svc_cls.side_effect = requests.exceptions.ConnectionError("refused")

    result = get_weather_data(latitude=42.0, longitude=-71.0)

    assert "error" in result


@patch("app.weather.WeatherService")
def test_get_weather_data_http_error(mock_svc_cls):
    """get_weather_data returns error dict on HTTPError."""
    mock_svc_cls.side_effect = requests.exceptions.HTTPError("503")

    result = get_weather_data(latitude=42.0, longitude=-71.0)

    assert "error" in result


# ── WeatherService config defaults ────────────────────────────────

def test_weather_service_reads_location_from_config():
    """With no arguments, WeatherService takes its coordinates from the config file.

    This is the path the web UI uses. It regressed silently when the config keys
    were renamed from lat/lon to latitude/longitude, because every other test
    passes coordinates explicitly.
    """
    svc = WeatherService()

    assert isinstance(svc.latitude, float)
    assert isinstance(svc.longitude, float)
    assert -90 <= svc.latitude <= 90
    assert -180 <= svc.longitude <= 180


# ── WeatherService.close ──────────────────────────────────────────

def test_close_without_session():
    """close() is safe when session was never created."""
    svc = WeatherService.__new__(WeatherService)
    svc.session = None
    svc.close()  # should not raise
