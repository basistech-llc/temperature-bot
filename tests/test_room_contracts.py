"""Room API write-contract tests."""

from app.device_types import DEVICE_TYPE_ERV, DEVICE_TYPE_FCU, DEVICE_TYPE_INTERNAL


def test_room_writes_reject_response_only_fcu_owner(flask_test_client):
    """Clients cannot forge FCU ownership during room creation or update."""
    rejected_create = flask_test_client.post(
        "/api/v1/rooms",
        json={"room_name": "Forged Owner", "fcu_device_id": 123},
    )
    assert rejected_create.status_code == 400
    assert rejected_create.json["error"] == "validation error"

    created = flask_test_client.post(
        "/api/v1/rooms",
        json={"room_name": "Mapless"},
    )
    assert created.status_code == 201
    room_id = created.json["room_id"]

    rejected_patch = flask_test_client.patch(
        f"/api/v1/rooms/{room_id}",
        json={"fcu_device_id": 123},
    )
    assert rejected_patch.status_code == 400
    assert rejected_patch.json["error"] == "validation error"

    unchanged = flask_test_client.get(f"/api/v1/rooms/{room_id}")
    assert unchanged.status_code == 200
    assert "fcu_device_id" not in unchanged.json


def test_room_writes_reserve_virtual_unassigned_name(flask_test_client):
    rejected_create = flask_test_client.post(
        "/api/v1/rooms", json={"room_name": " unASSIGNED "}
    )
    assert rejected_create.status_code == 400

    created = flask_test_client.post(
        "/api/v1/rooms", json={"room_name": "Assignable"}
    )
    rejected_patch = flask_test_client.patch(
        f"/api/v1/rooms/{created.json['room_id']}",
        json={"room_name": "UNASSIGNED"},
    )
    assert rejected_patch.status_code == 400


def test_room_list_is_typed_and_alphabetized(flask_test_client):
    for room_name in ("zulu", "Alpha", "bravo"):
        response = flask_test_client.post(
            "/api/v1/rooms", json={"room_name": room_name}
        )
        assert response.status_code == 201

    response = flask_test_client.get("/api/v1/rooms")
    assert response.status_code == 200
    assert [room["room_name"] for room in response.json["rooms"]] == [
        "Alpha",
        "bravo",
        "zulu",
    ]


def test_room_assignment_rejects_unknown_and_ineligible_devices(
    flask_test_client,
    test_database_conn_with_test_data,
):
    conn, _, _ = test_database_conn_with_test_data
    room_id = flask_test_client.post(
        "/api/v1/rooms", json={"room_name": "Allowed"}
    ).json["room_id"]
    other_room_id = flask_test_client.post(
        "/api/v1/rooms", json={"room_name": "Other"}
    ).json["room_id"]

    device_ids = {}
    for device_type in (DEVICE_TYPE_ERV, DEVICE_TYPE_INTERNAL, DEVICE_TYPE_FCU):
        cursor = conn.execute(
            "INSERT INTO devices (device_name, device_type) VALUES (?, ?)",
            (f"{device_type} Test", device_type),
        )
        device_ids[device_type] = cursor.lastrowid
    fcu_id = device_ids[DEVICE_TYPE_FCU]
    conn.execute(
        "UPDATE rooms SET fcu_device_id=? WHERE room_id=?", (fcu_id, room_id)
    )
    conn.execute("UPDATE devices SET room_id=? WHERE device_id=?", (room_id, fcu_id))
    conn.commit()

    unknown_device = flask_test_client.post(
        "/api/v1/update_device_room", json={"device_id": 999999, "room_id": room_id}
    )
    assert unknown_device.status_code == 404

    unknown_room = flask_test_client.post(
        "/api/v1/update_device_room",
        json={"device_id": fcu_id, "room_id": 999999},
    )
    assert unknown_room.status_code == 404

    for device_type in (DEVICE_TYPE_ERV, DEVICE_TYPE_INTERNAL):
        response = flask_test_client.post(
            "/api/v1/update_device_room",
            json={"device_id": device_ids[device_type], "room_id": room_id},
        )
        assert response.status_code == 409

    move_fcu = flask_test_client.post(
        "/api/v1/update_device_room",
        json={"device_id": fcu_id, "room_id": other_room_id},
    )
    assert move_fcu.status_code == 409
    keep_fcu = flask_test_client.post(
        "/api/v1/update_device_room",
        json={"device_id": fcu_id, "room_id": room_id},
    )
    assert keep_fcu.status_code == 200


def test_room_assignment_rejects_fcu_without_owned_room(
    flask_test_client, test_database_conn_with_test_data
):
    conn, _, _ = test_database_conn_with_test_data
    fcu_id = conn.execute(
        "INSERT INTO devices (device_name, device_type) VALUES ('Orphan FCU', 'FCU')"
    ).lastrowid
    conn.commit()

    response = flask_test_client.post(
        "/api/v1/update_device_room", json={"device_id": fcu_id, "room_id": None}
    )
    assert response.status_code == 409
    assert "owned room" in response.json["error"]


def test_room_assignment_and_rename_contracts_are_strict(flask_test_client):
    first = flask_test_client.post(
        "/api/v1/rooms", json={"room_name": "First"}
    )
    second = flask_test_client.post(
        "/api/v1/rooms", json={"room_name": "Second"}
    )
    assert first.status_code == 201
    assert second.status_code == 201

    duplicate_create = flask_test_client.post(
        "/api/v1/rooms", json={"room_name": "First"}
    )
    assert duplicate_create.status_code == 409
    duplicate_rename = flask_test_client.patch(
        f"/api/v1/rooms/{second.json['room_id']}", json={"room_name": "First"}
    )
    assert duplicate_rename.status_code == 409

    extra_assignment_field = flask_test_client.post(
        "/api/v1/update_device_room",
        json={"device_id": 1, "room_id": None, "room_name": "ignored"},
    )
    assert extra_assignment_field.status_code == 400
