"""Tests for air-quality helper utilities used by web routes."""

import datetime

from app.routes_web_airquality_utils import (
    score_air_metric,
    annotate_air_quality_cells,
    format_unix_as_asc,
)


def test_score_air_metric_co2_thresholds():
    """CO₂ metric should map to correct severity and short name."""
    assert score_air_metric("co2", 700) == (0, "good", "CO₂")
    assert score_air_metric("co2", 850)[0:2] == (1, "elevated")
    assert score_air_metric("co2", 1300)[0:2] == (2, "problem")


def test_score_air_metric_humidity_ranges():
    """Humidity ranges should yield elevated/problem as configured."""
    assert score_air_metric("humidity", 40)[0] == 0  # good
    assert score_air_metric("humidity", 32)[0] == 1  # elevated low
    assert score_air_metric("humidity", 62)[0] == 2  # problem high


def test_annotate_air_quality_cells_skips_outdoor_and_sets_classes():
    """Annotator should skip outdoor AQI rows and set classes for indoor metrics."""
    airmon = [
        {
            "device_id": 1,
            "device_name": "Area 51",
            "status": {
                "co2": {"value": 1300},  # problem
                "humidity": {"value": 40},  # good
            },
        },
        {
            "device_id": 0,
            "device_name": "Outdoor Air Quality",
            "status": {"aqi": {"value": 36}},
        },
    ]

    annotate_air_quality_cells(airmon)

    indoor = dict(airmon[0])
    outdoor = dict(airmon[1])

    aq_classes = indoor.get("aq_classes", {})
    assert aq_classes.get("co2") == "aq-problem"
    assert "humidity" not in aq_classes
    assert "aq_classes" not in outdoor


def test_format_unix_as_asc_none_and_value():
    """format_unix_as_asc should handle None and valid timestamps."""
    assert format_unix_as_asc(None) is None
    expected = datetime.datetime.fromtimestamp(0).strftime("%Y-%m-%d %H:%M:%S")
    assert format_unix_as_asc(0) == expected
