"""Integration coverage for canonical room dashboard membership."""

import json
import time

from app import db
from app.models import Room


def test_canonical_room_dashboard_tracks_rename_and_assignment(
    flask_test_client, test_database_conn_with_test_data
):
    conn, _, _ = test_database_conn_with_test_data
    room = db.create_room(conn, Room(room_name="Assigned Room"))
    other = db.create_room(conn, Room(room_name="Empty Room"))
    assert room.room_id is not None
    assert other.room_id is not None
    sensor_id = conn.execute(
        """
        INSERT INTO devices (device_name, display_name, device_type, room_id)
        VALUES ('Canonical Sensor', 'Friendly Sensor', 'SENSOR', ?)
        """,
        (room.room_id,),
    ).lastrowid
    conn.execute(
        """
        INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
        VALUES (?, ?, 1, 215, ?)
        """,
        (sensor_id, int(time.time()), json.dumps({"humidity": 42.6})),
    )
    conn.commit()

    response = flask_test_client.get(f"/room/{room.room_id}")
    assert response.status_code == 200
    assert b"Assigned Room" in response.data
    assert b"Friendly Sensor" in response.data
    assert b"21.5\xc2\xb0C" in response.data
    assert b"43%" in response.data

    db.update_room(conn, Room(room_id=room.room_id, room_name="Renamed Room"))
    renamed = flask_test_client.get(f"/room/{room.room_id}")
    assert b"Renamed Room" in renamed.data
    assert b"Friendly Sensor" in renamed.data

    conn.execute(
        "UPDATE devlog SET logtime=? WHERE device_id=?",
        (int(time.time()) - 700, sensor_id),
    )
    conn.commit()
    stale = flask_test_client.get(f"/room/{room.room_id}")
    assert b"Friendly Sensor" in stale.data
    assert b"Offline" in stale.data

    db.update_device_room(conn, sensor_id, other.room_id)
    moved = flask_test_client.get(f"/room/{room.room_id}")
    assert b"Friendly Sensor" not in moved.data
    assert b'<div class="sensors-card">' not in moved.data
