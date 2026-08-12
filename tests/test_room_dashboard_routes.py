"""Integration coverage for canonical room dashboard membership."""

import json
import logging
import re
import time

from app import db
from app.models import Room


def _add_sensor(conn, display_name, room_id, temp10x, humidity=None):
    """Create one assigned sensor with a fresh reading."""
    sensor_id = conn.execute(
        """
        INSERT INTO devices (device_name, display_name, device_type, room_id)
        VALUES (?, ?, 'SENSOR', ?)
        """,
        (display_name.lower().replace(" ", "-"), display_name, room_id),
    ).lastrowid
    conn.execute(
        """
        INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
        VALUES (?, ?, 1, ?, ?)
        """,
        (
            sensor_id,
            int(time.time()),
            temp10x,
            json.dumps({"humidity": humidity} if humidity is not None else {}),
        ),
    )
    conn.commit()
    return sensor_id


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
    # A reading past the freshness cutoff reports its age rather than claiming
    # the sensor is offline, which is not something this page can know.
    assert re.search(r"No data for \d+[smhd]", stale.data.decode())

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


def test_broadway_unions_the_sensors_of_every_member_room(
    flask_test_client, test_database_conn_with_test_data
):
    """One dashboard gathers sensors across the several rooms it is configured for.

    Broadway is served by two FCUs, and every FCU owns its own room, so the
    space cannot be one room. The dashboard spans them instead.
    """
    conn, _, _ = test_database_conn_with_test_data
    north = db.create_room(conn, Room(room_name="Broadway North"))
    south = db.create_room(conn, Room(room_name="Broadway South"))
    closet = db.create_room(conn, Room(room_name="Data Closet"))
    elsewhere = db.create_room(conn, Room(room_name="Bamboo"))
    _add_sensor(conn, "North Sensor", north.room_id, 231)
    _add_sensor(conn, "South Sensor", south.room_id, 239, humidity=58.4)
    _add_sensor(conn, "Closet Sensor", closet.room_id, 247)
    _add_sensor(conn, "Bamboo Sensor", elsewhere.room_id, 210)

    response = flask_test_client.get("/broadway")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "North Sensor" in body
    assert "South Sensor" in body
    assert "Closet Sensor" in body
    # A room the dashboard does not list stays off it.
    assert "Bamboo Sensor" not in body
    # Freshness and formatting still come from the shared selector.
    assert "23.1°C" in body
    assert "58%" in body


def test_broadway_renders_its_configured_controls(flask_test_client):
    """Each configured control renders one tile addressed by its own key."""
    response = flask_test_client.get("/broadway")
    body = response.get_data(as_text=True)

    assert 'data-control-key="pendant-lights"' in body
    assert "Pendant Lights" in body
    # The fan is a distinct kind, not an AE-200 card.
    assert 'data-control-kind="fan"' in body
    assert 'data-control-key="data-closet-fan"' in body
    assert 'data-speed="medium"' in body
    # Broadway has no TV lift.
    assert 'data-control-kind="tv"' not in body


def test_unresolvable_member_room_is_reported(
    flask_test_client, test_database_conn_with_test_data, caplog
):
    """Membership is keyed by name, so a rename must not silently drop a room."""
    conn, _, _ = test_database_conn_with_test_data
    north = db.create_room(conn, Room(room_name="Broadway North"))
    _add_sensor(conn, "North Sensor", north.room_id, 231)

    with caplog.at_level(logging.WARNING, logger="app.routes_web"):
        response = flask_test_client.get("/broadway")

    assert response.status_code == 200
    assert "North Sensor" in response.get_data(as_text=True)
    unresolved = [
        record.getMessage()
        for record in caplog.records
        if "matches no room name" in record.getMessage()
    ]
    assert len(unresolved) == 3
    assert any("Data Closet" in message for message in unresolved)


def test_single_room_dashboard_shows_only_its_own_room(
    flask_test_client, test_database_conn_with_test_data
):
    """A config with no members falls back to the room the URL addressed."""
    conn, _, _ = test_database_conn_with_test_data
    room = db.create_room(conn, Room(room_name="Solo Room"))
    other = db.create_room(conn, Room(room_name="Other Room"))
    _add_sensor(conn, "Solo Sensor", room.room_id, 220)
    _add_sensor(conn, "Other Sensor", other.room_id, 225)

    body = flask_test_client.get(f"/room/{room.room_id}").get_data(as_text=True)
    assert "Solo Sensor" in body
    assert "Other Sensor" not in body


def test_kitchen_membership_still_resolves_its_own_room(
    flask_test_client, test_database_conn_with_test_data
):
    """Kitchen must keep working now that membership comes from a config string.

    Broadway's multi-room union is covered above, but Kitchen is the plain
    single-member case, and a typo in its one members entry would render an
    empty dashboard while every other test still passed.
    """
    conn, _, _ = test_database_conn_with_test_data
    kitchen = db.create_room(conn, Room(room_name="Kitchen"))
    elsewhere = db.create_room(conn, Room(room_name="Bamboo"))
    _add_sensor(conn, "Lobby Sensor", kitchen.room_id, 230)
    _add_sensor(conn, "Bamboo Sensor", elsewhere.room_id, 210)

    body = flask_test_client.get("/kitchen").get_data(as_text=True)
    assert "Lobby Sensor" in body
    assert "Bamboo Sensor" not in body
    assert "23.0°C" in body


def test_kitchen_membership_follows_its_fcu_after_a_rename(
    flask_test_client, test_database_conn_with_test_data
):
    """A member key also matches the owning FCU, so a rename keeps the sensors.

    This is the whole reason membership is not keyed by room name alone.
    """
    conn, _, _ = test_database_conn_with_test_data
    conn.execute("INSERT INTO devices (device_name, device_type) VALUES ('Kitchen', 'FCU')")
    conn.commit()
    db.reconcile_fcu_rooms(conn)
    room = next(item for item in db.get_rooms(conn) if item.room_name == "Kitchen")
    db.update_room(conn, Room(room_id=room.room_id, room_name="Canteen"))
    _add_sensor(conn, "Lobby Sensor", room.room_id, 230)

    body = flask_test_client.get("/kitchen").get_data(as_text=True)
    assert "Lobby Sensor" in body
