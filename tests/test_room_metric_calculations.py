"""Integration tests for room-backed FCU metric calculations."""
# pylint: disable=duplicate-code

import json
import time

from app import db
from app.main import app
from app.models import Room


def _clear(conn):
    conn.execute("DELETE FROM fcu_temp_sources")
    conn.execute("DELETE FROM devlog")
    conn.execute("DELETE FROM devices")
    conn.execute("DELETE FROM rooms")
    conn.commit()
    db.DEVICE_MAP.clear()


def _device(conn, name, *, logtime, temp10x, status):
    device_id = db.get_or_create_device_id(conn, name, use_cache=False)
    conn.execute(
        """
        INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
        VALUES (?, ?, 0, ?, ?)
        """,
        (device_id, logtime, temp10x, json.dumps(status)),
    )
    conn.commit()
    return device_id


def _fcu_status():
    return {"Drive": "ON", "FanSpeed": "LOW", "Mode": "COOL"}


def test_room_move_updates_temperature_and_equal_weight_humidity(
    flask_test_client,
    test_database_conn_with_test_data,
):
    conn, _, _ = test_database_conn_with_test_data
    _clear(conn)
    now = int(time.time())
    room_id = db.create_room(conn, Room(room_name="Hickory")).room_id
    other_room_id = db.create_room(conn, Room(room_name="Kitchen")).room_id
    assert room_id is not None
    assert other_room_id is not None

    fcu_id = _device(
        conn, "Hickory FCU", logtime=now - 30, temp10x=200, status=_fcu_status()
    )
    weighted_id = _device(
        conn,
        "Hickory Weighted",
        logtime=now - 30,
        temp10x=260,
        status={"humidity": 40},
    )
    humidity_id = _device(
        conn,
        "Hickory Humidity",
        logtime=now - 30,
        temp10x=240,
        status={"humidity": 60},
    )
    for device_id in (fcu_id, weighted_id, humidity_id):
        db.update_device_room(conn, device_id, room_id)
    conn.executemany(
        """
        INSERT INTO fcu_temp_sources
            (fcu_device_id, source_device_id, multiplier, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        [(fcu_id, fcu_id, 1.0, now), (fcu_id, weighted_id, 1.0, now)],
    )
    conn.commit()

    assert db.calculate_fcu_temperature10x(conn, fcu_id) == 230
    assert db.calculate_fcu_humidities(conn, [fcu_id]) == {fcu_id: 50.0}

    moved = flask_test_client.post(
        "/api/v1/update_device_room",
        json={"device_id": weighted_id, "room_id": other_room_id},
    )
    assert moved.status_code == 200
    assert db.calculate_fcu_temperature10x(conn, fcu_id) == 200
    assert db.calculate_fcu_humidities(conn, [fcu_id]) == {fcu_id: 60.0}

    restored = flask_test_client.post(
        "/api/v1/update_device_room",
        json={"device_id": weighted_id, "room_id": room_id},
    )
    assert restored.status_code == 200
    assert db.calculate_fcu_temperature10x(conn, fcu_id) == 230
    statements = []
    conn.set_trace_callback(statements.append)
    try:
        status = db.get_device_status(conn)
    finally:
        conn.set_trace_callback(None)
    fcu = next(
        device for device in status if device["device_id"] == fcu_id
    )
    assert fcu["calculated_humidity"] == 50.0
    assert sum("ROW_NUMBER() OVER" in statement for statement in statements) == 1


def test_calculated_temperature_series_preserves_stale_gap(test_database_conn):
    conn = test_database_conn
    _clear(conn)
    base = 1_700_000_000
    fcu_id = _device(
        conn, "Gap FCU", logtime=base + 100, temp10x=200, status=_fcu_status()
    )
    sensor_id = _device(
        conn, "Gap Sensor", logtime=base + 50, temp10x=300, status={}
    )
    conn.execute(
        """
        INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
        VALUES (?, ?, 0, ?, ?)
        """,
        (fcu_id, base + 900, 200, json.dumps(_fcu_status())),
    )
    conn.executemany(
        """
        INSERT INTO fcu_temp_sources
            (fcu_device_id, source_device_id, multiplier, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        [(fcu_id, fcu_id, 0.0, base), (fcu_id, sensor_id, 1.0, base)],
    )
    conn.commit()

    with app.test_request_context(
        f"/api/v1/temperature?start={base + 100}&end={base + 900}"
    ):
        series = db.get_calculated_temperature_series(conn, [fcu_id])

    assert series[0]["data"] == [[base + 100, 30.0], [base + 900, None]]


def test_fcu_history_combines_labeled_temperature_and_state_series(
    flask_test_client, test_database_conn_with_test_data
):
    conn, _, _ = test_database_conn_with_test_data
    _clear(conn)
    base = int(time.time()) - 100
    fcu_id = _device(
        conn, "History FCU", logtime=base, temp10x=210, status=_fcu_status()
    )
    conn.execute(
        "UPDATE devices SET device_type='FCU' WHERE device_id=?", (fcu_id,)
    )
    room_id = db.create_room(conn, Room(room_name="History Room")).room_id
    assert room_id is not None
    conn.execute(
        "UPDATE rooms SET fcu_device_id=? WHERE room_id=?", (fcu_id, room_id)
    )
    conn.execute(
        "UPDATE devices SET room_id=? WHERE device_id=?", (room_id, fcu_id)
    )
    conn.commit()

    response = flask_test_client.get(
        f"/api/v1/fcu_history?fcu_device_id={fcu_id}"
    )
    assert response.status_code == 200
    assert response.json["room_name"] == "History Room"
    assert [item["name"] for item in response.json["temperature_series"]] == [
        "History Room - FCU inlet",
        "History Room - Room Temp",
    ]
    assert response.json["states"] == [
        {
            "timestamp": base,
            "mode": "COOL",
            "drive": "ON",
            "fan_speed": "LOW",
        }
    ]
