"""Persistent AE-200 notification collection tests."""

import asyncio

import pytest
import websockets

from app import ae200_notifications
from bin import ae200_notifications as collector

AUTH_RESPONSE = """<?xml version="1.0" encoding="UTF-8" ?>
<Packet><Command>getResponse</Command><DatabaseManager>
<WebUserAuth UserCategory="Administrator" UserName="Test" />
</DatabaseManager></Packet>"""

NOTIFICATION = """<?xml version="1.0" encoding="UTF-8" ?>
<Packet><Command>notifyRequest</Command><DatabaseManager>
<Mnet Group="10" Drive="ON" FanSpeed="HIGH" />
<Mnet Address="16" ThermoStatus="OFF" />
</DatabaseManager></Packet>"""


def test_parse_notification_preserves_group_address_and_changed_fields():
    events = ae200_notifications.parse_notification_frame(NOTIFICATION)
    assert len(events) == 2
    assert events[0].ae200_group_id == "10"
    assert events[0].ae200_address is None
    assert events[0].values == {"Drive": "ON", "FanSpeed": "HIGH"}
    assert events[1].ae200_group_id is None
    assert events[1].ae200_address == "16"
    assert events[1].values == {"ThermoStatus": "OFF"}


def test_parse_notification_rejects_response_frames():
    with pytest.raises(ValueError, match="expected notifyRequest"):
        ae200_notifications.parse_notification_frame(AUTH_RESPONSE)


def test_authentication_response_requires_valid_user_category():
    collector.validate_authentication_response(AUTH_RESPONSE)
    rejected = AUTH_RESPONSE.replace('UserCategory="Administrator"', 'UserCategory="none"')
    with pytest.raises(ConnectionError, match="authentication failed"):
        collector.validate_authentication_response(rejected)


def test_password_obfuscation_matches_protocol_and_rejects_unsupported_text():
    assert collector.encrypt_password("abc", "00001") == "acf"
    with pytest.raises(ValueError, match="must be alphanumeric"):
        collector.encrypt_password("not-valid", "00001")


def test_notification_retention_deletes_only_expired_rows(test_database_conn):
    now_ms = 100 * ae200_notifications.MILLISECONDS_PER_DAY
    events = [
        ae200_notifications.AE200Notification(
            observed_at_ms=now_ms - 91 * ae200_notifications.MILLISECONDS_PER_DAY,
            ae200_group_id="old",
            values={"Drive": "OFF"},
        ),
        ae200_notifications.AE200Notification(
            observed_at_ms=now_ms - 90 * ae200_notifications.MILLISECONDS_PER_DAY,
            ae200_group_id="boundary",
            values={"Drive": "ON"},
        ),
    ]
    ae200_notifications.insert_notifications(test_database_conn, events)

    assert ae200_notifications.delete_expired(
        test_database_conn, retention_days=90, now_ms=now_ms
    ) == 1
    page = ae200_notifications.fetch_recent(test_database_conn)
    assert [event.ae200_group_id for event in page.notifications] == ["boundary"]

    with pytest.raises(ValueError, match="at least 1"):
        ae200_notifications.delete_expired(test_database_conn, retention_days=0)


def test_collector_authenticates_and_persists_real_websocket_frame(
    test_database_conn,
):
    """Exercise authentication, notification parsing, and SQLite persistence."""

    async def exercise():
        async def handler(websocket):
            auth_request = await websocket.recv()
            assert "WebUserAuth" in auth_request
            assert 'User="administrator"' in auth_request
            await websocket.send(AUTH_RESPONSE)
            await websocket.send(NOTIFICATION)

        async with websockets.serve(
            handler, "127.0.0.1", 0, subprotocols=["b_xmlproc"]
        ) as server:
            port = server.sockets[0].getsockname()[1]
            return await collector.collect_notifications(
                f"127.0.0.1:{port}", "administrator", "", stop_after=2
            )

    assert asyncio.run(exercise()) == 2
    page = ae200_notifications.fetch_recent(test_database_conn)
    assert len(page.notifications) == 2
    assert page.notifications[0].values == {"ThermoStatus": "OFF"}
    assert page.notifications[1].values == {"Drive": "ON", "FanSpeed": "HIGH"}
