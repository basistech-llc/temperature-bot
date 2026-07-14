"""Substantive storage, policy, route, and rules coverage for room presence."""

from app import db, presence, rules_engine
from app.models import PresenceState, Room


def _room_and_sensor(conn, room_name: str, sensor_name: str) -> tuple[int, int]:
    room = db.create_room(conn, Room(room_name=room_name))
    assert room.room_id is not None
    cursor = conn.execute(
        """
        INSERT INTO devices (device_name, device_type, room_id)
        VALUES (?, 'SENSOR', ?)
        """,
        (sensor_name, room.room_id),
    )
    conn.commit()
    return room.room_id, int(cursor.lastrowid)


def test_presence_move_preserves_history_and_changes_current_room(test_database_conn):
    conn = test_database_conn
    first_room, sensor_id = _room_and_sensor(conn, "Presence A", "Motion A")
    second = db.create_room(conn, Room(room_name="Presence B"))
    assert second.room_id is not None

    db.record_presence_observation(
        conn, device_id=sensor_id, present=True, observed_at=1_000
    )
    assert rules_engine.get_room_presence(
        conn, first_room, when=1_010
    ).state == PresenceState.PRESENT

    db.update_device_room(conn, sensor_id, second.room_id)
    db.record_presence_observation(
        conn, device_id=sensor_id, present=False, observed_at=1_020
    )

    states = {room.room_id: room for room in presence.get_room_presence(conn, at_time=1_030)}
    assert states[first_room].state == PresenceState.UNKNOWN
    assert states[second.room_id].state == PresenceState.ABSENT
    history = db.get_presence_events(conn)
    assert [(event.room_id, event.present) for event in history] == [
        (second.room_id, False),
        (first_room, True),
    ]


def test_presence_policy_distinguishes_stale_from_unknown(test_database_conn):
    conn = test_database_conn
    room_id, sensor_id = _room_and_sensor(conn, "Presence Stale", "Motion Stale")
    empty = db.create_room(conn, Room(room_name="Presence Unknown"))
    assert empty.room_id is not None
    db.record_presence_observation(
        conn, device_id=sensor_id, present=True, observed_at=2_000
    )

    states = {
        room.room_id: room
        for room in presence.get_room_presence(
            conn,
            at_time=2_000 + presence.PRESENCE_STALE_SECONDS + 1,
        )
    }
    assert states[room_id].state == PresenceState.STALE
    assert states[empty.room_id].state == PresenceState.UNKNOWN


def test_presence_api_and_table_use_canonical_policy(
    flask_test_client, test_database_conn_with_test_data
):
    conn, _, _ = test_database_conn_with_test_data
    room_id, sensor_id = _room_and_sensor(conn, "Presence Route", "Motion Route")
    db.record_presence_observation(conn, device_id=sensor_id, present=True)

    current = flask_test_client.get("/api/v1/presence")
    assert current.status_code == 200
    room = next(item for item in current.json["rooms"] if item["room_id"] == room_id)
    assert room["state"] == "present"
    assert room["source_device_ids"] == [sensor_id]

    history = flask_test_client.get(f"/api/v1/presence/history?room_id={room_id}")
    assert history.status_code == 200
    assert history.json["events"][0]["room_name"] == "Presence Route"

    table = flask_test_client.get("/presence")
    assert table.status_code == 200
    assert b"Presence Route" in table.data
    assert b"Present" in table.data
