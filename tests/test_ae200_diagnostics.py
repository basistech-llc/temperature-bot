"""AE-200 diagnostics page and typed audit API tests."""

import xml.etree.ElementTree as ET

import pytest
from websockets.exceptions import WebSocketException

from conftest import flask_test_client  # noqa: F401  # pylint: disable=unused-import

from app import ae200, ae200_command_log, ae200_notifications


def test_ae200_page_links_live_performance_and_command_sections(flask_test_client):  # noqa: F811
    response = flask_test_client.get("/ae200")
    assert response.status_code == 200
    html = response.data
    assert b"Real-time controller data" in html
    assert b"AE-200 request performance" in html
    assert b"Last 50 commands" in html
    assert b'/static/ae200_page.js' in html
    assert b'href="/ae200" class="pure-menu-selected"' in html


def test_ae200_status_preserves_schedule_and_raw_controller_fields(flask_test_client):  # noqa: F811
    response = flask_test_client.get("/api/v1/ae200/status")
    assert response.status_code == 200
    snapshot = response.json
    assert snapshot["simulator"] is True
    assert snapshot["units"]
    assert {"device_id", "name", "status"} <= snapshot["units"][0].keys()
    assert "Schedule" in snapshot["units"][0]["status"]
    assert "ScheduleAvail" in snapshot["units"][0]["status"]


@pytest.mark.parametrize(
    "error", [WebSocketException("disconnected"), ET.ParseError("malformed XML")]
)
def test_ae200_status_isolates_transport_and_xml_errors(
    error, monkeypatch, flask_test_client
):  # noqa: F811
    def fail_device_read(_device_id):
        raise error

    monkeypatch.setattr(ae200, "get_device_info", fail_device_read)
    response = flask_test_client.get("/api/v1/ae200/status")
    assert response.status_code == 200
    assert response.json["units"]
    assert all(unit["error"].endswith(str(error)) for unit in response.json["units"])


def test_ae200_command_api_returns_latest_parsed_command(flask_test_client):  # noqa: F811
    ae200.set_fcu_state(10, drive=1, fan_speed=4)
    response = flask_test_client.get("/api/v1/ae200/commands?limit=1")
    assert response.status_code == 200
    command = response.json["commands"][0]
    assert command["ae200_device_id"] == "10"
    assert command["request"] == {"Drive": "ON", "FanSpeed": "HIGH"}
    assert command["outcome"] == "simulated"
    assert command["response_summary"] == "simulated: Drive=ON FanSpeed=HIGH"

    invalid = flask_test_client.get("/api/v1/ae200/commands?limit=0")
    assert invalid.status_code == 400


def test_ae200_command_error_is_bounded_and_queryable(test_database_conn):
    record = ae200_command_log.new_record("10", {"Drive": "ON"})
    ae200_command_log.mark_error(record, RuntimeError("x" * 1000))
    ae200_command_log.insert_record(test_database_conn, record)
    test_database_conn.commit()

    command = ae200_command_log.fetch_recent(test_database_conn, limit=1).commands[0]
    assert command.outcome == "error"
    assert command.error_type == "RuntimeError"
    assert command.error_message == "x" * ae200_command_log.MAX_ERROR_LENGTH
    assert len(command.response_summary) == ae200_command_log.MAX_ERROR_LENGTH


def test_ae200_notification_api_returns_unattributed_observations(
    flask_test_client, test_database_conn
):  # noqa: F811
    event = ae200_notifications.AE200Notification(
        ae200_group_id="10", values={"Drive": "OFF"}
    )
    ae200_notifications.insert_notifications(test_database_conn, [event])
    test_database_conn.commit()

    response = flask_test_client.get("/api/v1/ae200/notifications?limit=50")
    assert response.status_code == 200
    assert response.json["notifications"][0]["ae200_group_id"] == "10"
    assert response.json["notifications"][0]["values"] == {"Drive": "OFF"}
