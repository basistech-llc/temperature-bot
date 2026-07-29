"""Substantive server-rendered room matrix grouping tests."""

import re
import time

from app.models import Room
from app.dashboard_views import room_matrix_groups


def _with_display_fields(devices):
    """Supply the display fields room_matrix_groups requires, and nothing else.

    annotate_device_rows() cannot be used here: it recomputes
    dashboard_air_quality_active from logtime/temp10x, which these fixtures
    deliberately omit. The grouping behavior under test is about that flag's
    value, not about how it is derived.
    """
    for device in devices:
        name = device["device_name"]
        device.setdefault("device_label", name)
        device.setdefault("device_label_with_icon", name)
        device.setdefault("device_update_text", "")
        device.setdefault("device_update_tooltip", name)
    return devices


def test_room_matrix_groups_include_empty_rooms_and_unassigned():
    devices = [
        {
                "device_id": 4,
                "device_name": "Zulu FCU",
                "device_type": "FCU",
                "room_id": 2,
                "calculated_temp10x": 215,
                "calculated_humidity": 42.6,
            },
            {
                "device_id": 8,
                "device_name": "Zulu assigned sensor",
                "device_type": "SENSOR",
                "room_id": 2,
                "dashboard_air_quality_active": True,
            },
            {
                "device_id": 7,
                "device_name": "Alpha assigned sensor",
                "device_type": "SENSOR",
                "room_id": 2,
                "dashboard_air_quality_active": True,
            },
            {
                "device_id": 9,
                "device_name": "Loose sensor",
                "device_type": "SENSOR",
                "dashboard_air_quality_active": True,
            },
    ]
    groups = room_matrix_groups(
        _with_display_fields(devices),
        [
            Room(room_id=2, room_name="Zulu"),
            Room(room_id=1, room_name="Alpha"),
        ],
        {2},
    )

    assert [group.room_name for group in groups] == ["Alpha", "Unassigned", "Zulu"]
    assert groups[0].devices == []
    assert [device.device_name for device in groups[1].devices] == ["Loose sensor"]
    assert [device.device_name for device in groups[2].devices] == [
        "Alpha assigned sensor",
        "Zulu assigned sensor",
    ]
    assert groups[2].fcu_device_id == 4
    assert groups[2].calculated_temp10x == 215
    assert groups[2].calculated_humidity == 42.6


def test_room_matrix_groups_exclude_non_sensor_infrastructure_rows():
    devices = [
        {
                "device_id": device_id,
                "device_name": device_type,
                "device_type": device_type,
                "room_id": 1,
                "dashboard_air_quality_active": True,
            }
            for device_id, device_type in enumerate(
                ["FCU", "ERV", "INTERNAL"], start=1
            )
    ]
    groups = room_matrix_groups(
        _with_display_fields(devices),
        [Room(room_id=1, room_name="Alpha")],
        {1},
    )

    assert [group.room_name for group in groups] == ["Alpha", "Unassigned"]
    assert all(not group.devices for group in groups)


def test_index_renders_room_sections_and_each_sensor_once(
    flask_test_client, test_database_conn_with_test_data
):
    conn, _, _ = test_database_conn_with_test_data
    alpha_id = conn.execute(
        "INSERT INTO rooms (room_name) VALUES ('Alpha')"
    ).lastrowid
    conn.execute("INSERT INTO rooms (room_name) VALUES ('Bravo')")
    charlie_id = conn.execute(
        "INSERT INTO rooms (room_name) VALUES ('Charlie')"
    ).lastrowid
    zulu_id = conn.execute(
        "INSERT INTO rooms (room_name) VALUES ('Zulu')"
    ).lastrowid
    now = int(time.time())
    device_ids = {}
    for name, device_type, room_id in (
        ("Assigned Sensor", "SENSOR", zulu_id),
        ("Loose Sensor", "SENSOR", None),
        ("Internal Reading", "INTERNAL", alpha_id),
    ):
        device_id = conn.execute(
            """
            INSERT INTO devices (device_name, device_type, room_id)
            VALUES (?, ?, ?)
            """,
            (name, device_type, room_id),
        ).lastrowid
        conn.execute(
            """
            INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
            VALUES (?, ?, 1, 220, '{"humidity": 40}')
            """,
            (device_id, now),
        )
        device_ids[name] = device_id
    conn.commit()
    conn.execute(
        """
        INSERT INTO devices (device_name, device_type, room_id)
        VALUES ('New sensor without readings', 'SENSOR', ?)
        """,
        (charlie_id,),
    )
    conn.commit()

    response = flask_test_client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    room_names = re.findall(
        r'<tr class="room-separator"\s+data-room-id="[^"]*"\s+'
        r'data-room-name="([^"]+)"[^>]*>',
        html,
    )

    assert room_names == ["Alpha", "Bravo", "Charlie", "Unassigned", "Zulu"]
    assert re.search(
        r'data-room-name="Alpha"\s+data-has-fcu="false"\s+data-can-delete="false"',
        html,
    )
    assert re.search(
        r'data-room-name="Bravo"\s+data-has-fcu="false"\s+data-can-delete="true"',
        html,
    )
    assert re.search(
        r'data-room-name="Charlie"\s+data-has-fcu="false"\s+data-can-delete="false"',
        html,
    )
    assert re.search(
        r'data-room-name="Zulu"\s+data-has-fcu="false"\s+data-can-delete="false"',
        html,
    )
    assert "Air Quality and Room Assignments" in html
    assert 'id="new-room-button"' in html
    assert 'id="room-create-dialog"' in html
    assert 'id="room-delete-dialog"' in html
    assert "Assigned Sensor 📡" in html
    assert html.count(f'x-data-device-id="{device_ids["Assigned Sensor"]}"') == 1
    assert html.count(f'x-data-device-id="{device_ids["Loose Sensor"]}"') == 1
    assert f'x-data-device-id="{device_ids["Internal Reading"]}"' not in html
