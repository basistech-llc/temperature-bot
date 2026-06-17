"""Tests for air-quality helper utilities used by web routes."""

import datetime
import time

from app.routes_web_airquality_utils import annotate_staleness, format_unix_as_asc


def test_annotate_staleness_marks_old_rows_stale():
    """Staleness annotation should flag rows whose last sample is over five minutes old."""
    now = int(time.time())
    airmon = [
        {"logtime": now - 60, "duration": 1},
        {"logtime": now - 400, "duration": 1},
        {},
    ]

    annotate_staleness(airmon)

    assert airmon[0]["is_stale"] is False
    assert airmon[0]["age"]
    assert airmon[1]["is_stale"] is True
    assert airmon[1]["age"]
    assert airmon[2]["is_stale"] is False
    assert airmon[2]["age"] is None


def test_format_unix_as_asc_none_and_value():
    """format_unix_as_asc should handle None and valid timestamps."""
    assert format_unix_as_asc(None) is None
    expected = datetime.datetime.fromtimestamp(0).strftime("%Y-%m-%d %H:%M:%S")
    assert format_unix_as_asc(0) == expected
