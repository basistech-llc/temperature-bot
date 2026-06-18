"""Tests for current FCU status display fallbacks."""

import json
import time

from app import db
from app.constants import TEMP_SOURCE_STALE_SECONDS


def _clear_devices(conn):
    conn.execute("DELETE FROM fcu_set_ranges")
    conn.execute("DELETE FROM fcu_temp_sources")
    conn.execute("DELETE FROM devlog")
    conn.execute("DELETE FROM devices")
    conn.execute("DELETE FROM rooms")
    conn.commit()
    db.DEVICE_MAP.clear()


def _fcu_status():
    return {"Drive": "ON", "FanSpeed": "LOW", "Mode": "COOL", "InletTemp": "21.5"}


def test_status_room_temp_defaults_to_stale_raw_fcu_temp(test_database_conn):
    conn = test_database_conn
    _clear_devices(conn)
    now = int(time.time())
    fcu_id = db.get_or_create_device_id(conn, "Stale Default FCU", use_cache=False)
    conn.execute(
        """
        INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            fcu_id,
            now - TEMP_SOURCE_STALE_SECONDS - 90,
            1,
            215,
            json.dumps(_fcu_status()),
        ),
    )
    conn.commit()

    assert db.calculate_fcu_temperature10x(conn, fcu_id) is None
    status = db.get_device_status(conn)
    fcu = next(device for device in status if device["device_id"] == fcu_id)
    assert fcu["temp10x"] == 215
    assert fcu["calculated_temp10x"] == 215
