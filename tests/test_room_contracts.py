"""Room API write-contract tests."""


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
