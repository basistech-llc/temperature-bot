"""Integrated canonical-room behavior across the principal room consumers."""

import re
import time

from app import db
from app.models import Room


def test_room_identity_move_rename_and_staleness_reach_all_consumers(
    flask_test_client, test_database_conn_with_test_data
):
    conn, _, _ = test_database_conn_with_test_data
    now = int(time.time())
    fcu_id = db.get_or_create_device_id(
        conn, "Integration FCU", device_type="FCU"
    )
    room_id = conn.execute(
        "SELECT room_id FROM devices WHERE device_id=?", (fcu_id,)
    ).fetchone()[0]
    sensor_id = conn.execute(
        """
        INSERT INTO devices (device_name, display_name, device_type)
        VALUES ('Integration Sensor', 'Integration Display', 'SENSOR')
        """
    ).lastrowid
    db.insert_devlog_entry(
        conn,
        device_id=fcu_id,
        temp=20,
        statusdict={"InletTemp": "20", "Mode": "COOL", "Drive": "ON"},
        logtime=now,
    )
    db.insert_devlog_entry(
        conn,
        device_id=sensor_id,
        temp=22,
        statusdict={"humidity": 41, "motion": "active"},
        logtime=now,
    )

    unassigned = flask_test_client.get("/").data
    assert b"Unassigned" in unassigned
    assert b"Integration Display" in unassigned

    db.update_device_room(conn, sensor_id, room_id)
    db.record_presence_observation(
        conn, device_id=sensor_id, present=True, observed_at=now
    )
    db.update_room(conn, Room(room_id=room_id, room_name="Renamed Integration"))

    topology = flask_test_client.get("/api/v1/rooms").json["rooms"]
    assert next(room for room in topology if room["room_id"] == room_id)[
        "room_name"
    ] == "Renamed Integration"
    status = flask_test_client.get("/api/v1/status").json["devices"]
    assigned = next(device for device in status if device["device_id"] == sensor_id)
    assert assigned["room_id"] == room_id
    assert assigned["room_name"] == "Renamed Integration"
    assert b"Integration Display" in flask_test_client.get(f"/room/{room_id}").data
    presence = flask_test_client.get("/api/v1/presence").json["rooms"]
    assert next(room for room in presence if room["room_id"] == room_id)[
        "state"
    ] == "present"
    history = flask_test_client.get(
        f"/api/v1/fcu_history?fcu_device_id={fcu_id}"
    ).json
    assert history["room_name"] == "Renamed Integration"

    conn.execute(
        "UPDATE devlog SET logtime=?, duration=1 WHERE device_id IN (?, ?)",
        (now - 1_000, fcu_id, sensor_id),
    )
    conn.execute(
        "UPDATE presence_events SET observed_at=? WHERE device_id=?",
        (now - 1_000, sensor_id),
    )
    conn.commit()

    stale_status = flask_test_client.get("/api/v1/status").json["devices"]
    stale_fcu = next(device for device in stale_status if device["device_id"] == fcu_id)
    assert stale_fcu.get("calculated_temp10x") is None
    assert stale_fcu.get("calculated_humidity") is None
    stale_page = flask_test_client.get("/").data.decode()
    assert re.search(
        rf'id="room-summary-temp-{room_id}"[^>]*>--', stale_page
    )
    assert b"Offline" in flask_test_client.get(f"/room/{room_id}").data
    stale_presence = flask_test_client.get("/api/v1/presence").json["rooms"]
    assert next(room for room in stale_presence if room["room_id"] == room_id)[
        "state"
    ] == "stale"
