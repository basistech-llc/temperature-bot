"""Verified, atomic FCU command tests."""

import os
import sqlite3
import time

from conftest import flask_test_client  # noqa: F401  # pylint: disable=unused-import

from app import ae200, db
from app.constants import TEST_DB_NAME
from app.models import ChangelogAction

AE200_UNIT = 10


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
