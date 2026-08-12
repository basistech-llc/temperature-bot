"""The ``set_body_*`` HVAC command path, driven directly against the simulator.

Two properties are covered here. Commanded state must survive a stale hardware
read-back, and every manual change must describe itself in ``changelog.comment``
as ``<what changed> <old> -> <new>``, with names substituted for the raw AE-200
wire codes that drive and fan speed are logged as.
"""

import json
import os
import sqlite3
from unittest.mock import patch

import pytest
from conftest import flask_test_client  # noqa: F401  # pylint: disable=unused-import

from app import ae200, db, rules_engine
from app.models import (
    AutoSetTempControl,
    DriveControl,
    SetTempControl,
    SpeedControl,
)

BROADWAY_SOUTH = 10

# Set points are bare strings here, exactly as the AE-200 reports them.
FCU_STATUS = {
    "Drive": "ON",
    "FanSpeed": "LOW",
    "SetTemp": "24",
    "SetTemp1": "24",
    "SetTemp2": "19",
    "InletTemp": "22.0",
}


def _link_device_to_unit(conn, name):
    """Create a device linked to the BROADWAY_SOUTH simulator unit; return its id."""
    device_id = db.get_or_create_device_id(conn, name)
    conn.execute(
        "UPDATE devices SET ae200_device_id=? WHERE device_id=?",
        (BROADWAY_SOUTH, device_id),
    )
    conn.commit()
    return device_id


def _latest_devlog_status(conn, device_id):
    """Return the extracted drive/fan_speed of the most recent devlog row."""
    row = conn.execute(
        "SELECT status_json FROM devlog WHERE device_id=? ORDER BY logtime DESC",
        (device_id,),
    ).fetchone()
    return ae200.extract_drive_and_fan_speed(json.loads(row["status_json"]))


def _latest_changelog(conn, device_id):
    """Return the most recent changelog row for one device."""
    return conn.execute(
        "SELECT current_values, new_value, comment FROM changelog "
        "WHERE device_id=? ORDER BY changelog_id DESC LIMIT 1",
        (device_id,),
    ).fetchone()


def _changelog_count(conn, device_id):
    return conn.execute(
        "SELECT COUNT(*) AS n FROM changelog WHERE device_id=?", (device_id,)
    ).fetchone()["n"]


def test_set_body_drive_records_commanded_state_and_names_it(
    test_database_conn,
):  # noqa: F811
    """The unit is ON and we command OFF, while the read-back still reports the
    stale ON (the read-back can race the command).

    Two regressions: the recorded status must be the commanded OFF, or /status
    reports the stale drive and the UI snaps back to the prior selection; and the
    changelog must name the states, because its columns hold only wire codes
    (1 -> 0).
    """
    conn = test_database_conn
    device_id = _link_device_to_unit(conn, "Drive Command Test")

    with patch.object(ae200, "get_device_drive", return_value=1), patch.object(
        ae200, "set_drive"
    ) as mock_set_drive, patch.object(
        ae200, "get_device_info", return_value=dict(FCU_STATUS)
    ):
        rules_engine.set_body_drive(
            conn,
            DriveControl(device_id=device_id, drive=0),
            "127.0.0.1",
            "web",
        )
        mock_set_drive.assert_called_once()

    assert _latest_devlog_status(conn, device_id)["drive"] == 0
    row = _latest_changelog(conn, device_id)
    assert (row["current_values"], row["new_value"]) == ("1", "0")
    assert row["comment"] == "drive ON -> OFF"


def test_set_body_fan_speed_records_commanded_speed_and_names_it(
    test_database_conn,
):  # noqa: F811
    """The unit is on LOW (1) and we command MID1 (3), while the read-back still
    reports the stale LOW.

    Same pair of regressions as the drive case: record the commanded speed, and
    name the speeds the logged wire codes (1 -> 3) stand for.
    """
    conn = test_database_conn
    device_id = _link_device_to_unit(conn, "Fan Speed Command Test")

    with patch.object(ae200, "get_device_fan_speed", return_value=1), patch.object(
        ae200, "set_fan_speed"
    ) as mock_set_speed, patch.object(
        ae200, "get_device_info", return_value=dict(FCU_STATUS)
    ):
        rules_engine.set_body_fan_speed(
            conn,
            SpeedControl(device_id=device_id, fan_speed=3),
            "127.0.0.1",
            "web",
        )
        mock_set_speed.assert_called_once()

    assert _latest_devlog_status(conn, device_id)["fan_speed"] == 3
    row = _latest_changelog(conn, device_id)
    assert (row["current_values"], row["new_value"]) == ("1", "3")
    assert row["comment"] == "fan speed LOW -> MID1"


def test_set_temp_comment_describes_the_change(test_database_conn):  # noqa: F811
    """A real set-point change spells out both set points and the unit."""
    conn = test_database_conn
    device_id = _link_device_to_unit(conn, "Set Temp Comment Test")

    with patch.object(ae200, "set_set_temp") as mock_set_temp, patch.object(
        ae200, "get_device_info", return_value=dict(FCU_STATUS)
    ):
        rules_engine.set_body_set_temp(
            conn,
            SetTempControl(device_id=device_id, set_temp_c=21.5),
            "127.0.0.1",
            "web",
        )
        mock_set_temp.assert_called_once()

    row = _latest_changelog(conn, device_id)
    assert (row["current_values"], row["new_value"]) == ("24", "21.5")
    assert row["comment"] == "set temp 24 -> 21.5 C"


def test_auto_temps_comment_names_absent_setpoints(test_database_conn):  # noqa: F811
    """A unit that has never run in AUTO reports no SetTemp1/SetTemp2 at all --
    ae200.cleanDeviceInfo strips empty values, so the keys are simply missing.

    Without a fallback the comment read "set auto temps Heat= Cool= -> ...": a
    self-describing audit row that describes nothing on the left.
    """
    conn = test_database_conn
    device_id = _link_device_to_unit(conn, "Auto Temps Never Run Test")
    absent = ("SetTemp1", "SetTemp2")
    status = {k: v for k, v in FCU_STATUS.items() if k not in absent}

    with patch.object(ae200, "set_auto_set_temps") as mock_set_auto, patch.object(
        ae200, "get_device_info", return_value=status
    ):
        rules_engine.set_body_auto_set_temp(
            conn,
            AutoSetTempControl(
                device_id=device_id, heat_set_temp_c=19.0, cool_set_temp_c=24.0
            ),
            "127.0.0.1",
            "web",
        )
        mock_set_auto.assert_called_once()

    row = _latest_changelog(conn, device_id)
    assert row["comment"] == (
        "set auto temps Heat=unknown Cool=unknown -> Heat=19 Cool=24"
    )


@pytest.mark.parametrize(
    "label,ae200_setter,command,make_control",
    [
        (
            "set temp",
            "set_set_temp",
            "set_body_set_temp",
            lambda device_id: SetTempControl(device_id=device_id, set_temp_c=24.0),
        ),
        (
            "set auto temps",
            "set_auto_set_temps",
            "set_body_auto_set_temp",
            lambda device_id: AutoSetTempControl(
                device_id=device_id, heat_set_temp_c=19.0, cool_set_temp_c=24.0
            ),
        ),
    ],
)
def test_non_canonical_setpoint_string_is_not_a_change(
    test_database_conn, label, ae200_setter, command, make_control
):  # noqa: F811
    """Regression: the AE-200 reports its set points as bare strings ("24"), so
    comparing them as strings against the float request read 24 -> 24.0 as a change.
    That both logged a spurious changelog row -- now a labelled one, which is worse
    -- and re-sent a command that changes nothing."""
    conn = test_database_conn
    device_id = _link_device_to_unit(conn, f"No-Op Test: {label}")

    before = _changelog_count(conn, device_id)
    with patch.object(ae200, ae200_setter) as mock_setter, patch.object(
        ae200, "get_device_info", return_value=dict(FCU_STATUS)
    ):
        getattr(rules_engine, command)(
            conn, make_control(device_id), "127.0.0.1", "web"
        )
        mock_setter.assert_not_called()

    assert _changelog_count(conn, device_id) == before


def test_fan_speed_endpoint_comments_both_rows(flask_test_client):  # noqa: F811
    """/set_fan_speed writes two changelog rows -- the speed change and the
    rules-disable it triggers -- and neither may be blank."""
    ae200.set_fan_speed(BROADWAY_SOUTH, 1)

    conn = sqlite3.connect(os.environ["TEST_DB_NAME"])
    conn.row_factory = sqlite3.Row
    try:
        device_id = _link_device_to_unit(conn, "Fan Speed Endpoint Comment Test")
    finally:
        conn.close()

    response = flask_test_client.post(
        "/api/v1/set_fan_speed",
        json={"device_id": device_id, "fan_speed": 4},
    )
    assert response.status_code == 200

    conn = sqlite3.connect(os.environ["TEST_DB_NAME"])
    conn.row_factory = sqlite3.Row
    try:
        comments = [
            row["comment"]
            for row in conn.execute(
                "SELECT comment FROM changelog WHERE device_id=? "
                "ORDER BY changelog_id DESC LIMIT 2",
                (device_id,),
            ).fetchall()
        ]
    finally:
        conn.close()

    assert len(comments) == 2
    assert any(c.startswith("fan speed ") for c in comments), comments
    assert any(c.startswith("Rules disabled for ") for c in comments), comments


def test_disable_rules_endpoint_records_who_and_why(flask_test_client):  # noqa: F811
    """/disable-rules is the master rules switch and was the last manual control
    writing a wholly blank audit row.

    disable_all_rules called db.disable_rules_for_device positionally, so comment,
    ipaddr and agent were all NULL -- an unattributable row in the logs table.
    """
    response = flask_test_client.get("/api/v1/disable-rules?seconds=3600")
    assert response.status_code == 200

    conn = sqlite3.connect(os.environ["TEST_DB_NAME"])
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT ipaddr, agent, comment FROM changelog ORDER BY changelog_id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    assert row["comment"] == "all rules disabled for 60 minutes"
    assert row["ipaddr"] == "127.0.0.1"
    assert row["agent"]
