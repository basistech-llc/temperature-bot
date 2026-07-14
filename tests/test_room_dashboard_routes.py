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


def test_configured_controls_follow_owned_fcu_after_room_rename(
    flask_test_client, test_database_conn_with_test_data
):
    conn, _, _ = test_database_conn_with_test_data
    fcu_id = conn.execute(
        "INSERT INTO devices (device_name, device_type) VALUES ('Hickory', 'FCU')"
    ).lastrowid
    conn.commit()
    db.reconcile_fcu_rooms(conn)
    room = next(item for item in db.get_rooms(conn) if item.fcu_device_id == fcu_id)
    assert room.room_id is not None
    db.update_room(conn, Room(room_id=room.room_id, room_name="Library"))

    canonical = flask_test_client.get(f"/room/{room.room_id}")
    assert canonical.status_code == 200
    assert b'data-room-control-key="hickory"' in canonical.data
    assert b"Library" in canonical.data

    legacy = flask_test_client.get("/hickory")
    assert legacy.status_code == 200
    assert b'data-room-control-key="hickory"' in legacy.data
    assert b"Library" in legacy.data
