"""AE-200 diagnostics page and typed audit API tests."""

from conftest import flask_test_client  # noqa: F401  # pylint: disable=unused-import

from app import ae200, ae200_notifications


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
