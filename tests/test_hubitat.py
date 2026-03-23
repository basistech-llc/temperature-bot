"""
Tests for Hubitat integration helpers.
"""

import logging
from os.path import join
import json
from unittest.mock import patch

import pytest

from app import hubitat
from app.paths import ETC_DIR
from bin import runner

logger = logging.getLogger(__name__)

HUBITAT_JSON = join(ETC_DIR, "sample_hubitat.json")


def _load_sample_devices():
    with open(HUBITAT_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_hubitat_extract_temperatures_numeric_fields():
    """extract_temperatures normalizes numeric attributes and exposes status payload."""
    hubdict = _load_sample_devices()
    temps = hubitat.extract_temperatures(hubdict)
    assert len(temps) == 15

    # Pick a representative device from the sample with known values.
    dungeon = next(t for t in temps if t["name"] == "Dungeon Meter")

    # Top-level temperature is a float, not a string.
    assert dungeon["temperature"] == pytest.approx(19.4)

    status = dungeon["status"]
    attrs = status["attributes"]

    # Status copies are numeric.
    assert status["temperature"] == pytest.approx(19.4)
    assert status["humidity"] == 15
    assert status["illuminance"] == 78

    # Attributes are also normalized to numbers where appropriate.
    assert attrs["temperature"] == pytest.approx(19.4)
    assert attrs["humidity"] == 15
    assert attrs["illuminance"] == 78


@patch("bin.runner.hubitat.get_all_devices")
def test_update_from_hubitat_persists_status_json(
    mock_get_all_devices, test_database_conn
):
    """update_from_hubitat writes both temp10x and rich status_json for Hubitat devices."""
    hubdict = _load_sample_devices()
    mock_get_all_devices.return_value = hubdict

    conn = test_database_conn

    # Run the updater against the test DB.
    runner.update_from_hubitat(conn)

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT d.device_name, l.temp10x, l.status_json
        FROM devices d
        JOIN devlog l ON d.device_id = l.device_id
        WHERE d.device_name = ?
        ORDER BY l.logtime DESC
        LIMIT 1
        """,
        ("Dungeon Meter",),
    )
    row = cursor.fetchone()
    assert row is not None

    # Temperature stored in temp10x matches the normalized value.
    assert row["temp10x"] == pytest.approx(194)  # 19.4 * 10

    status = json.loads(row["status_json"])
    # The persisted status carries numeric humidity and illuminance.
    assert status["name"] == "Dungeon Meter"
    assert status["temperature"] == pytest.approx(19.4)
    assert status["humidity"] == 15
    assert status["illuminance"] == 78
