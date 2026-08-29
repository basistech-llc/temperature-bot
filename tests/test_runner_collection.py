"""Collection-only runner behavior."""

import json

from bin import runner


def test_read_only_ae200_collection_persists_state_without_alerts(
    test_database_conn,
):
    status = {
        "InletTemp": "22.5",
        "ErrorSign": "ON",
        "FilterSign": "OFF",
        "CheckWater": "OFF",
    }

    runner.process_device_alert_data(
        test_database_conn,
        {"id": "12", "name": "Stage Unit"},
        status,
        observed_at=100,
        evaluate_alerts=False,
    )
    test_database_conn.commit()

    device = test_database_conn.execute(
        "SELECT device_id FROM devices WHERE device_name = 'Stage Unit'"
    ).fetchone()
    reading = test_database_conn.execute(
        "SELECT temp10x, status_json FROM devlog WHERE device_id = ?",
        (device["device_id"],),
    ).fetchone()
    assert reading["temp10x"] == 225
    assert json.loads(reading["status_json"])["ErrorSign"] == "ON"
    assert test_database_conn.execute("SELECT count(*) FROM alerts").fetchone()[0] == 0
