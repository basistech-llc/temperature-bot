"""Contract tests for the uniform ``/api/v1`` error envelope.

Every API failure must answer with the same JSON shape regardless of which
validation style the route uses, so browser code and future clients can rely on
one contract. See ``app/api_errors.py``.
"""

import pytest

from app import api_errors, models

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
    # Room and rules controls, converted from hand-rolled checks in Step 4
    ("POST", "/api/v1/hickory/dimmer", {"level": 500}, 400, "validation_error"),
    ("POST", "/api/v1/hickory/wall_light", {"light": "sideways"}, 400,
     "validation_error"),
    ("POST", "/api/v1/hickory/tv", {"direction": "sideways"}, 400,
     "validation_error"),
    ("POST", "/api/v1/rules_master", {}, 400, "validation_error"),
    ("POST", "/api/v1/set_device_disabled_until", {}, 400, "validation_error"),
    # Query-string checks
    ("GET", "/api/v1/temperature?mode=bogus", None, 400, "bad_request"),
    ("GET", "/api/v1/temperature?device_ids=abc", None, 400, "bad_request"),
    ("GET", "/api/v1/lighting?device_ids=abc", None, 400, "bad_request"),
    ("GET", "/api/v1/metric?metric=nosuchmetric", None, 400, "bad_request"),
    ("GET", "/api/v1/disable-rules", None, 400, "validation_error"),
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


def test_db_conflict_is_not_flattened_to_bad_request(flask_test_client, monkeypatch):  # noqa: F811
    """A db-raised Conflict must keep its 409 status.

    ``Conflict`` subclasses ``ValueError`` so non-route callers catching the
    builtin keep working. That makes route error handling order-sensitive: an
    ``except ValueError`` arm that does not let ``ApiError`` through first would
    silently downgrade every domain conflict to a generic 400.
    """
    def conflict(*_args, **_kwargs):
        raise api_errors.Conflict("room is still in use")

    monkeypatch.setattr("app.routes_api.db.delete_empty_room", conflict)
    response = flask_test_client.delete("/api/v1/rooms/1")

    assert response.status_code == 409
    body = response.get_json()
    assert body["code"] == "conflict"
    assert body["error"] == "room is still in use"


def test_db_not_found_keeps_its_status(flask_test_client, monkeypatch):  # noqa: F811
    """A db-raised NotFound reaches the client as 404, not 400 or 500."""
    def missing(*_args, **_kwargs):
        raise api_errors.NotFound("Unknown device_id: 4242")

    monkeypatch.setattr("app.routes_api.db.update_device_room", missing)
    response = flask_test_client.post(
        "/api/v1/update_device_room",
        json={"device_id": 4242, "room_id": None},
    )

    assert response.status_code == 404
    assert response.get_json()["code"] == "not_found"


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


def test_alert_rows_keep_nulls_but_omit_absent_details():
    """Alert rows mix two serialization conventions; both must survive.

    ``json_ready``'s ``exclude_none`` would drop ``end_time`` from an
    unresolved alert, and a plain dump would emit ``"details": null`` for a
    caller that did not ask for details. ``alert_json_ready`` is the reason
    these endpoints do not use ``json_ready``.
    """
    unresolved = models.AlertHistoryEntry.model_validate(
        {
            "alert_id": 1,
            "device_name": "d",
            "alert_type": "t",
            "alert_value": "ON",
            "start_time": 100,
            "end_time": None,
            "duration": None,
        }
    )
    dumped = models.alert_json_ready(unresolved)
    assert dumped["end_time"] is None
    assert dumped["duration"] is None
    assert "details" not in dumped

    with_details = models.ActiveAlert.model_validate(
        {
            "alert_id": 1,
            "device_name": "d",
            "alert_type": "t",
            "alert_value": "ON",
            "start_time": 100,
            "age": 5,
            "details": {"mode": "COOL"},
        }
    )
    assert models.alert_json_ready(with_details)["details"] == {"mode": "COOL"}
