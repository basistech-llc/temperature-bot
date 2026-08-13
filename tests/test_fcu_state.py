"""Verified, atomic FCU command tests."""

import os
import json
import sqlite3
import time
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ValidationError

from conftest import flask_test_client  # noqa: F401  # pylint: disable=unused-import

from app import ae200, db, fcu_control, rules_engine
from app.constants import TEST_DB_NAME
from app.models import ChangelogAction, DriveControl, SpeedControl

AE200_UNIT = 10


class UnconfirmedCase(BaseModel):
    """Inputs and expected audit state for one stale controller response."""

    command: str
    control: DriveControl | SpeedControl
    status: dict[str, str]
    field: str
    value: int
    action: ChangelogAction


@pytest.mark.parametrize(
    ("payload", "expected_drive", "expected_speed"),
    [
        ({"device_id": 1, "drive": "on", "fan_speed": "high"}, 1, 4),
        ({"device_id": 1, "drive": " 0 ", "fan_speed": " -1 "}, 0, -1),
    ],
)
def test_fcu_state_contract_normalizes_named_and_numeric_controls(
    payload, expected_drive, expected_speed
):
    command = fcu_control.FcuStateControl.model_validate(payload)
    assert command.drive == expected_drive
    assert command.fan_speed == expected_speed


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"device_id": 1}, "drive or fan_speed is required"),
        ({"device_id": 1, "drive": 9}, "unknown drive"),
        ({"device_id": 1, "drive": "running"}, "unknown drive"),
        ({"device_id": 1, "drive": []}, "valid integer"),
        ({"device_id": 1, "fan_speed": []}, "unknown fan_speed"),
        ({"device_id": 1, "fan_speed": 9}, "unknown fan_speed"),
        ({"device_id": 1, "fan_speed": "turbo"}, "unknown fan_speed"),
    ],
)
def test_fcu_state_contract_rejects_missing_or_unknown_controls(payload, message):
    with pytest.raises(ValidationError, match=message):
        fcu_control.FcuStateControl.model_validate(payload)


def test_fcu_state_endpoint_reports_controller_protocol_failure(
    monkeypatch, flask_test_client
):  # noqa: F811
    def fail_command(*_args, **_kwargs):
        raise ae200.AE200VerificationError(
            "AE-200 returned getResponse for setRequest"
        )

    monkeypatch.setattr("app.routes_api.rules_engine.set_body_fcu_state", fail_command)
    response = flask_test_client.post(
        "/api/v1/set_fcu_state",
        json={"device_id": 1, "drive": 1, "fan_speed": 4},
    )
    assert response.status_code == 502
    assert response.json == {
        "error": "AE-200 did not confirm requested state",
        "code": "upstream_unavailable",
    }


@pytest.mark.parametrize(
    "case",
    [
        UnconfirmedCase(
            command="set_body_drive",
            control=DriveControl(device_id=1, drive=0),
            status={"Drive": "ON", "FanSpeed": "AUTO", "InletTemp": "22.0"},
            field="drive",
            value=1,
            action=ChangelogAction.DRIVE,
        ),
        UnconfirmedCase(
            command="set_body_fan_speed",
            control=SpeedControl(device_id=1, fan_speed=3),
            status={"Drive": "ON", "FanSpeed": "LOW", "InletTemp": "22.0"},
            field="fan_speed",
            value=1,
            action=ChangelogAction.FAN_SPEED,
        ),
    ],
)
def test_fcu_control_rejects_unconfirmed_readback(case, test_database_conn):
    """A stale read-back is audited and recorded, never manufactured as success."""
    conn = test_database_conn
    device_id = db.get_or_create_device_id(conn, f"Unconfirmed {case.action.value}")
    conn.execute(
        "UPDATE devices SET ae200_device_id=? WHERE device_id=?",
        (AE200_UNIT, device_id),
    )
    conn.commit()
    control = case.control.model_copy(update={"device_id": device_id})

    with patch.object(
        ae200, "get_device_info", return_value=dict(case.status)
    ), patch.object(ae200, "set_fcu_state"), patch.object(
        ae200, "get_device_info_after_write", return_value=dict(case.status)
    ):
        with pytest.raises(ae200.AE200VerificationError):
            getattr(rules_engine, case.command)(conn, control, "127.0.0.1", "web")

    row = conn.execute(
        "SELECT status_json FROM devlog WHERE device_id=? ORDER BY logtime DESC",
        (device_id,),
    ).fetchone()
    assert ae200.extract_drive_and_fan_speed(json.loads(row["status_json"]))[
        case.field
    ] == case.value
    audit = conn.execute(
        "SELECT action, comment FROM changelog WHERE device_id=?",
        (device_id,),
    ).fetchone()
    assert audit["action"] == case.action.value
    assert audit["comment"].startswith("not confirmed")


def test_set_fcu_state_is_atomic_verified_and_logged_once(flask_test_client):  # noqa: F811
    """One dashboard selection writes one state and one suspension audit row."""
    ae200.set_fcu_state(AE200_UNIT, drive=0, fan_speed=-1)
    with sqlite3.connect(os.environ[TEST_DB_NAME]) as conn:
        conn.row_factory = sqlite3.Row
        device_id = db.get_or_create_device_id(conn, "Atomic FCU State Test")
        conn.execute(
            "UPDATE devices SET ae200_device_id=? WHERE device_id=?",
            (AE200_UNIT, device_id),
        )
        conn.commit()

    response = flask_test_client.post(
        "/api/v1/set_fcu_state",
        json={"device_id": device_id, "drive": 1, "fan_speed": 4},
    )

    assert response.status_code == 200
    assert response.json["verified"] is True
    assert response.json["drive"] == 1
    assert response.json["speed"] == 4
    assert ae200.get_device_info(AE200_UNIT)["Drive"] == "ON"
    assert ae200.get_device_info(AE200_UNIT)["FanSpeed"] == "HIGH"

    with sqlite3.connect(os.environ[TEST_DB_NAME]) as conn:
        rows = conn.execute(
            """
            SELECT action, current_values, new_value, comment
            FROM changelog
            WHERE device_id=?
            ORDER BY changelog_id
            """,
            (device_id,),
        ).fetchall()
    assert rows[0] == (
        ChangelogAction.FCU_STATE.value,
        "Drive=OFF FanSpeed=AUTO",
        "Drive=ON FanSpeed=HIGH",
        "confirmed",
    )
    assert len(rows) == 2
    assert rows[1][0] == ChangelogAction.RULES_SUSPENSION.value
    assert rows[1][1] == ""
    assert int(rows[1][2]) >= int(time.time()) + 179 * 60
    assert rows[1][3] == "Rules disabled for 180 minutes"

    with sqlite3.connect(os.environ[TEST_DB_NAME]) as conn:
        command = conn.execute(
            """
            SELECT request_json, outcome, response_summary
            FROM ae200_command_log
            WHERE ae200_device_id=?
            ORDER BY command_id DESC LIMIT 1
            """,
            (str(AE200_UNIT),),
        ).fetchone()
    assert json.loads(command[0]) == {"Drive": "ON", "FanSpeed": "HIGH"}
    assert command[1] == "simulated"
    assert command[2] == "simulated: Drive=ON FanSpeed=HIGH"
