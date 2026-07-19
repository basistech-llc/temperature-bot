"""Strict validation tests for hardware and configuration control requests."""

import pytest


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    (
        ("POST", "/api/v1/set_fan_speed", {"device_id": 1, "fan_speed": 1}),
        (
            "POST",
            "/api/v1/set_fcu_state",
            {"device_id": 1, "drive": 1, "fan_speed": 1},
        ),
        ("POST", "/api/v1/set_drive", {"device_id": 1, "drive": 1}),
        ("POST", "/api/v1/set_mode", {"device_id": 1, "mode": "COOL"}),
        ("POST", "/api/v1/set_temp", {"device_id": 1, "set_temp_c": 21}),
        (
            "POST",
            "/api/v1/set_auto_temp",
            {"device_id": 1, "heat_set_temp_c": 19, "cool_set_temp_c": 24},
        ),
        (
            "POST",
            "/api/v1/set_range",
            {"device_id": 1, "set_range_low_c": 19, "set_range_high_c": 24},
        ),
        ("POST", "/api/v1/update_note", {"device_id": 1, "notes": "note"}),
        (
            "POST",
            "/api/v1/update_device_room",
            {"device_id": 1, "room_id": None},
        ),
        (
            "POST",
            "/api/v1/fcu_temp_source",
            {"fcu_device_id": 1, "source_device_id": 2, "multiplier": 1},
        ),
        ("PATCH", "/api/v1/devices/1", {"display_name": "Unit"}),
    ),
)
def test_control_endpoints_reject_unknown_fields(
    flask_test_client, method, path, payload
):
    response = flask_test_client.open(
        path,
        method=method,
        json={**payload, "unexpected": True},
    )

    assert response.status_code == 400
