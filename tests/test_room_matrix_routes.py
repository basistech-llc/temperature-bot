"""Substantive server-rendered room matrix grouping tests."""

from app.models import Room
from app.routes_web import _room_matrix_groups


def test_room_matrix_groups_include_empty_rooms_and_unassigned():
    groups = _room_matrix_groups(
        [
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
                "device_name": "Assigned sensor",
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
        ],
        [
            Room(room_id=2, room_name="Zulu"),
            Room(room_id=1, room_name="Alpha"),
        ],
    )

    assert [group.room_name for group in groups] == ["Alpha", "Unassigned", "Zulu"]
    assert groups[0].devices == []
    assert [device.device_name for device in groups[1].devices] == ["Loose sensor"]
    assert [device.device_name for device in groups[2].devices] == ["Assigned sensor"]
    assert groups[2].fcu_device_id == 4
    assert groups[2].calculated_temp10x == 215
    assert groups[2].calculated_humidity == 42.6
