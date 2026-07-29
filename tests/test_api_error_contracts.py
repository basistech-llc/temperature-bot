"""Contract tests for the uniform ``/api/v1`` error envelope.

Every API failure must answer with the same JSON shape regardless of which
validation style the route uses, so browser code and future clients can rely on
one contract. See ``app/api_errors.py``.
"""

import pytest

from tests.conftest import flask_test_client  # noqa: F401  pylint: disable=unused-import


# (method, path, payload, expected status, expected code)
ERROR_CASES = [
    # flask_pydantic @validate() decorated bodies
    ("POST", "/api/v1/set_fan_speed", {}, 400, "validation_error"),
    ("POST", "/api/v1/set_drive", {}, 400, "validation_error"),
    ("POST", "/api/v1/set_mode", {"device_id": 1, "mode": "SETBACK"}, 400,
     "validation_error"),
    ("POST", "/api/v1/set_temp", {}, 400, "validation_error"),
    ("POST", "/api/v1/set_auto_temp", {}, 400, "validation_error"),
    ("POST", "/api/v1/update_note", {}, 400, "validation_error"),
    ("POST", "/api/v1/update_device_room", {}, 400, "validation_error"),
    # Models validated by hand inside the route
    ("POST", "/api/v1/rooms", {}, 400, "validation_error"),
    ("POST", "/api/v1/fcu_temp_source", {}, 400, "validation_error"),
    # Hand-rolled request checks
    ("POST", "/api/v1/hickory/dimmer", {"level": 500}, 400, "bad_request"),
    ("POST", "/api/v1/hickory/wall_light", {"light": "sideways"}, 400, "bad_request"),
    ("POST", "/api/v1/hickory/tv", {"direction": "sideways"}, 400, "bad_request"),
    ("POST", "/api/v1/rules_master", {}, 400, "bad_request"),
    ("POST", "/api/v1/set_device_disabled_until", {}, 400, "bad_request"),
    # Query-string checks
    ("GET", "/api/v1/temperature?mode=bogus", None, 400, "bad_request"),
    ("GET", "/api/v1/temperature?device_ids=abc", None, 400, "bad_request"),
    ("GET", "/api/v1/lighting?device_ids=abc", None, 400, "bad_request"),
    ("GET", "/api/v1/metric?metric=nosuchmetric", None, 400, "bad_request"),
    ("GET", "/api/v1/disable-rules", None, 400, "bad_request"),
    ("GET", "/api/v1/fcu_history", None, 400, "bad_request"),
    ("GET", "/api/v1/fcu_temp_sources", None, 400, "bad_request"),
    # Not-found paths
    ("GET", "/api/v1/rooms/999999", None, 404, "not_found"),
    ("GET", "/api/v1/presence/history?room_id=999999", None, 404, "not_found"),
    ("GET", "/api/v1/room/nosuchroom/room_status", None, 404, "not_found"),
    ("POST", "/api/v1/room/nosuchroom/dimmer", {"level": 50}, 404, "not_found"),
    ("GET", "/api/v1/fcu_history?fcu_device_id=999999", None, 404, "not_found"),
    ("GET", "/api/v1/fcu_temp_sources?fcu_device_id=999999", None, 404, "not_found"),
    ("POST", "/api/v1/update_device_room", {"device_id": 999999, "room_id": None},
     404, "not_found"),
]


@pytest.mark.parametrize(
    "case",
    ERROR_CASES,
    ids=[f"{m}:{p}" for m, p, _, _, _ in ERROR_CASES],
)
def test_api_errors_share_one_envelope(flask_test_client, case):  # noqa: F811
    """Every failure returns error/code, and details only as a list."""
    method, path, payload, expected_status, expected_code = case
    response = flask_test_client.open(path, method=method, json=payload)

    assert response.status_code == expected_status
    body = response.get_json()
    assert body["code"] == expected_code
    # Browser code renders `error` directly, so it must stay a non-empty string.
    assert isinstance(body["error"], str) and body["error"]
    if "details" in body:
        assert isinstance(body["details"], list)
        assert body["details"], "details must be omitted rather than sent empty"


def test_validation_errors_name_the_offending_field(flask_test_client):  # noqa: F811
    """The human-readable message stays specific enough to show a user."""
    response = flask_test_client.post("/api/v1/set_fan_speed", json={})

    assert response.status_code == 400
    body = response.get_json()
    assert "device_id" in body["error"]
    assert {entry["location"] for entry in body["details"]} == {"body"}


def test_decorated_and_manual_validation_agree(flask_test_client):  # noqa: F811
    """A @validate() route and a hand-validated route report failures alike."""
    decorated = flask_test_client.post("/api/v1/set_fan_speed", json={}).get_json()
    manual = flask_test_client.post("/api/v1/rooms", json={}).get_json()

    assert decorated.keys() == manual.keys() == {"error", "code", "details"}
    assert decorated["code"] == manual["code"] == "validation_error"
    for body in (decorated, manual):
        for entry in body["details"]:
            assert {"loc", "msg", "type", "location"} <= entry.keys()


def test_unexpected_errors_do_not_leak_exception_text(flask_test_client, monkeypatch):  # noqa: F811
    """An unhandled exception returns a generic body, not the message."""
    def explode(*_args, **_kwargs):
        raise KeyError("s3cret-connection-string")

    monkeypatch.setattr("app.routes_api.db.get_rules_master_enabled", explode)
    response = flask_test_client.get("/api/v1/rules_master")

    assert response.status_code == 500
    assert response.get_json() == {
        "error": "Internal server error",
        "code": "internal_error",
    }
    assert "s3cret" not in response.get_data(as_text=True)
