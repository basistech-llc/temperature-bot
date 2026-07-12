"""Tests for editable device metadata."""

import os
import sqlite3

from conftest import flask_test_client  # noqa: F401  # pylint: disable=unused-import


def _first_device_id() -> int:
    test_db_path = os.environ.get("TEST_DB_NAME")
    assert test_db_path
    with sqlite3.connect(test_db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT device_id FROM devices ORDER BY device_id LIMIT 1"
        ).fetchone()["device_id"]


def test_device_metadata_api_updates_fields(flask_test_client):  # noqa: F811
    """Device metadata endpoint should persist display/type/rules settings."""
    device_id = _first_device_id()

    response = flask_test_client.patch(
        f"/api/v1/devices/{device_id}",
        json={
            "display_name": "South FCU",
            "device_type": "fcu",
            "rules_enabled": False,
            "notes": "metadata test",
        },
    )

    assert response.status_code == 200
    assert response.json["display_name"] == "South FCU"
    assert response.json["device_type"] == "FCU"
    assert response.json["rules_enabled"] is False

    test_db_path = os.environ["TEST_DB_NAME"]
    with sqlite3.connect(test_db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT display_name, device_type, rules_enabled, notes
            FROM devices
            WHERE device_id=?
            """,
            (device_id,),
        ).fetchone()
    assert row["display_name"] == "South FCU"
    assert row["device_type"] == "FCU"
    assert row["rules_enabled"] == 0
    assert row["notes"] == "metadata test"


def test_device_metadata_empty_patch_preserves_fields(flask_test_client):  # noqa: F811
    """PATCH with no editable fields should not clear existing metadata."""
    device_id = _first_device_id()
    test_db_path = os.environ["TEST_DB_NAME"]
    with sqlite3.connect(test_db_path) as conn:
        conn.execute(
            """
            UPDATE devices
            SET display_name=?, device_type=?, rules_enabled=?, notes=?
            WHERE device_id=?
            """,
            ("Existing Name", "ERV", 0, "keep this note", device_id),
        )
        conn.commit()

    response = flask_test_client.patch(f"/api/v1/devices/{device_id}", json={})

    assert response.status_code == 200
    assert response.json["display_name"] == "Existing Name"
    assert response.json["device_type"] == "ERV"
    assert response.json["rules_enabled"] is False
    assert response.json["notes"] == "keep this note"

    with sqlite3.connect(test_db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT display_name, device_type, rules_enabled, notes
            FROM devices
            WHERE device_id=?
            """,
            (device_id,),
        ).fetchone()
    assert row["display_name"] == "Existing Name"
    assert row["device_type"] == "ERV"
    assert row["rules_enabled"] == 0
    assert row["notes"] == "keep this note"


def test_devices_route(flask_test_client):  # noqa: F811
    """Device editor page should render."""
    response = flask_test_client.get("/devices")
    assert response.status_code == 200
    assert b"Display Name" in response.data
    assert b"<th>ID</th>" not in response.data
    assert b'datalist id="device-types"' not in response.data
    assert b'name="device_type_' not in response.data


def test_devices_route_updates_metadata(flask_test_client):  # noqa: F811
    """Posting the device editor form persists editable fields but not type."""
    device_id = _first_device_id()
    test_db_path = os.environ["TEST_DB_NAME"]
    with sqlite3.connect(test_db_path) as conn:
        conn.execute(
            "UPDATE devices SET device_type=? WHERE device_id=?",
            ("FCU", device_id),
        )
        conn.commit()

    response = flask_test_client.post(
        "/devices",
        data={
            "device_id": str(device_id),
            f"display_name_{device_id}": "Editor Name",
            f"device_type_{device_id}": "sensor",  # Ignored even if forged.
            f"rules_enabled_{device_id}": "1",
            f"notes_{device_id}": "editor note",
        },
    )
    assert response.status_code == 302

    with sqlite3.connect(test_db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT display_name, device_type, rules_enabled, notes
            FROM devices
            WHERE device_id=?
            """,
            (device_id,),
        ).fetchone()
    assert row["display_name"] == "Editor Name"
    assert row["device_type"] == "FCU"
    assert row["rules_enabled"] == 1
    assert row["notes"] == "editor note"
