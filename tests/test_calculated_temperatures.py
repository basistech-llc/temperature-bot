"""Tests for room metadata and calculated FCU temperatures."""
# pylint: disable=duplicate-code

from contextlib import closing
from dataclasses import dataclass
import json
import os
import sqlite3
import time

from app import db, rules_engine
from app.constants import TEMP_SOURCE_STALE_SECONDS
from app.main import app
from app.models import Room


@dataclass(frozen=True)
class TempDeviceSpec:
    """Device fixture fields for calculated-temperature tests."""

    name: str
    temp10x: int
    logtime: int
    duration: int = 60
    status: dict | None = None
    aqi_mon: int = 0


@dataclass(frozen=True)
class TempRowSpec:
    """One devlog row for calculated-temperature history tests."""

    device_id: int
    logtime: int
    temp10x: int
    duration: int = 60
    status: dict | None = None


def _clear_devices(conn):
    conn.execute("DELETE FROM fcu_temp_sources")
    conn.execute("DELETE FROM devlog")
    conn.execute("DELETE FROM devices")
    conn.execute("DELETE FROM rooms")
    conn.commit()
    db.DEVICE_MAP.clear()


def _device(conn, spec: TempDeviceSpec):
    device_id = db.get_or_create_device_id(conn, spec.name, use_cache=False)
    conn.execute(
        "UPDATE devices SET aqi_mon=? WHERE device_id=?",
        (spec.aqi_mon, device_id),
    )
    conn.execute(
        """
        INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            device_id,
            spec.logtime,
            spec.duration,
            spec.temp10x,
            json.dumps(spec.status or {}),
        ),
    )
    conn.commit()
    return device_id


def _insert_temp_row(conn, spec: TempRowSpec):
    conn.execute(
        """
        INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            spec.device_id,
            spec.logtime,
            spec.duration,
            spec.temp10x,
            json.dumps(spec.status or {}),
        ),
    )


def _fcu_status():
    return {"Drive": "ON", "FanSpeed": "LOW", "Mode": "COOL", "InletTemp": "20.0"}


def test_default_fcu_weight_used_when_no_source_rows(test_database_conn):
    conn = test_database_conn
    _clear_devices(conn)
    now = int(time.time())

    fcu_id = _device(
        conn,
        TempDeviceSpec(
            name="Default FCU",
            temp10x=215,
            logtime=now - 30,
            status=_fcu_status(),
        ),
    )
    sensor_id = _device(
        conn, TempDeviceSpec(name="Default Wall Sensor", temp10x=260, logtime=now - 30)
    )

    first_weights = db.get_fcu_temp_source_weights(conn, fcu_id)
    second_weights = db.get_fcu_temp_source_weights(conn, fcu_id)
    assert first_weights == {fcu_id: 1.0}
    assert second_weights == first_weights
    rows = conn.execute(
        """
        SELECT source_device_id, multiplier
        FROM fcu_temp_sources
        WHERE fcu_device_id=?
        """,
        (fcu_id,),
    ).fetchall()
    assert rows == []
    assert db.calculate_fcu_temperature10x(conn, fcu_id) == 215

    status = db.get_device_status(conn)
    fcu = next(device for device in status if device["device_id"] == fcu_id)
    assert fcu["calculated_temp10x"] == 215
    rows = conn.execute(
        """
        SELECT source_device_id, multiplier
        FROM fcu_temp_sources
        WHERE fcu_device_id=?
        """,
        (fcu_id,),
    ).fetchall()
    assert rows == []

    response = db.get_fcu_temp_sources(conn, fcu_id)
    by_id = {source["source_device_id"]: source for source in response["sources"]}
    assert by_id[fcu_id]["multiplier"] == 1.0
    assert by_id[fcu_id]["included"] is True
    assert by_id[sensor_id]["multiplier"] == 0.0
    assert by_id[sensor_id]["included"] is False
    rows = conn.execute(
        """
        SELECT source_device_id, multiplier
        FROM fcu_temp_sources
        WHERE fcu_device_id=?
        """,
        (fcu_id,),
    ).fetchall()
    assert rows == []


def test_explicit_zero_fcu_weight_overrides_default(test_database_conn):
    conn = test_database_conn
    _clear_devices(conn)
    now = int(time.time())

    fcu_id = _device(
        conn,
        TempDeviceSpec(
            name="Zero Weight FCU",
            temp10x=215,
            logtime=now - 30,
            status=_fcu_status(),
        ),
    )

    response = db.set_fcu_temp_source_multiplier(
        conn,
        fcu_device_id=fcu_id,
        source_device_id=fcu_id,
        multiplier=0.0,
        ipaddr=None,
        agent=None,
    )

    row = conn.execute(
        """
        SELECT multiplier
        FROM fcu_temp_sources
        WHERE fcu_device_id=? AND source_device_id=?
        """,
        (fcu_id, fcu_id),
    ).fetchone()
    assert row["multiplier"] == 0.0
    assert db.get_fcu_temp_source_weights(conn, fcu_id) == {fcu_id: 0.0}
    assert db.calculate_fcu_temperature10x(conn, fcu_id) is None
    source = next(
        item for item in response["sources"] if item["source_device_id"] == fcu_id
    )
    assert source["multiplier"] == 0.0
    assert source["included"] is False


def test_calculated_temperature_weights_fcu_and_sources_excluding_stale(
    test_database_conn,
):
    conn = test_database_conn
    _clear_devices(conn)
    now = int(time.time())

    fcu_id = _device(
        conn,
        TempDeviceSpec(
            name="Hickory FCU",
            temp10x=200,
            logtime=now - 60,
            status=_fcu_status(),
        ),
    )
    fresh_id = _device(
        conn, TempDeviceSpec(name="Wall Sensor", temp10x=260, logtime=now - 30)
    )
    stale_id = _device(
        conn,
        TempDeviceSpec(
            name="Old Sensor",
            temp10x=300,
            logtime=now - TEMP_SOURCE_STALE_SECONDS - 90,
            duration=1,
        ),
    )

    conn.executemany(
        """
        INSERT INTO fcu_temp_sources
            (fcu_device_id, source_device_id, multiplier, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        [
            (fcu_id, fcu_id, 2.0, now),
            (fcu_id, fresh_id, 1.0, now),
            (fcu_id, stale_id, 100.0, now),
        ],
    )
    conn.commit()

    assert db.calculate_fcu_temperature10x(conn, fcu_id) == 220

    status = db.get_device_status(conn)
    fcu = next(device for device in status if device["device_id"] == fcu_id)
    assert fcu["calculated_temp10x"] == 220
    assert fcu["temp_source_stale_seconds"] == TEMP_SOURCE_STALE_SECONDS


def test_fcu_temp_sources_include_any_temperature_reporting_device(
    test_database_conn,
):
    conn = test_database_conn
    _clear_devices(conn)
    now = int(time.time())

    fcu_id = _device(
        conn,
        TempDeviceSpec(
            name="Area 51",
            temp10x=210,
            logtime=now - 20,
            status=_fcu_status(),
        ),
    )
    airthings_id = _device(
        conn,
        TempDeviceSpec(
            name="Airthings Lab",
            temp10x=230,
            logtime=now - 20,
            aqi_mon=1,
        ),
    )
    hubitat_id = _device(
        conn,
        TempDeviceSpec(name="Hubitat Room Sensor", temp10x=240, logtime=now - 20),
    )
    conn.execute(
        """
        INSERT INTO fcu_temp_sources
            (fcu_device_id, source_device_id, multiplier, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (fcu_id, hubitat_id, 0.75, now),
    )
    conn.commit()

    response = db.get_fcu_temp_sources(conn, fcu_id)
    by_id = {source["source_device_id"]: source for source in response["sources"]}

    assert airthings_id in by_id
    assert hubitat_id in by_id
    assert by_id[fcu_id]["is_fcu_self"] is True
    assert by_id[hubitat_id]["multiplier"] == 0.75
    assert by_id[hubitat_id]["included"] is True


def test_temperature_rules_context_prefers_calculated_fcu_temp(
    test_database_conn, monkeypatch
):
    conn = test_database_conn
    _clear_devices(conn)
    now = int(time.time())

    fcu_id = _device(
        conn,
        TempDeviceSpec(
            name="Broadway South",
            temp10x=200,
            logtime=now - 30,
            status=_fcu_status(),
        ),
    )
    sensor_id = _device(
        conn, TempDeviceSpec(name="Broadway Sensor", temp10x=260, logtime=now - 30)
    )
    conn.executemany(
        """
        INSERT INTO fcu_temp_sources
            (fcu_device_id, source_device_id, multiplier, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        [(fcu_id, fcu_id, 1.0, now), (fcu_id, sensor_id, 1.0, now)],
    )
    conn.execute("INSERT INTO aqi (logtime, aqi) VALUES (?, ?)", (now, 45))
    conn.commit()

    monkeypatch.setattr(
        rules_engine,
        "get_rules",
        lambda: (
            "if get_temp(BROADWAY_SOUTH) == 23.0:\n"
            "    set_fan_speed(BROADWAY_SOUTH, 3)\n"
        ),
    )

    assert (
        rules_engine.rules_results(conn, when=now)
        == f"Device {fcu_id} speed set to 3"
    )


def test_temperature_rules_context_exposes_raw_fcu_temp(
    test_database_conn, monkeypatch
):
    conn = test_database_conn
    _clear_devices(conn)
    now = int(time.time())

    fcu_id = _device(
        conn,
        TempDeviceSpec(
            name="Rule Raw FCU",
            temp10x=200,
            logtime=now - 30,
            status=_fcu_status(),
        ),
    )
    sensor_id = _device(
        conn, TempDeviceSpec(name="Rule Sensor", temp10x=260, logtime=now - 30)
    )
    conn.executemany(
        """
        INSERT INTO fcu_temp_sources
            (fcu_device_id, source_device_id, multiplier, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        [(fcu_id, fcu_id, 1.0, now), (fcu_id, sensor_id, 1.0, now)],
    )
    conn.execute("INSERT INTO aqi (logtime, aqi) VALUES (?, ?)", (now, 45))
    conn.commit()

    monkeypatch.setattr(
        rules_engine,
        "get_rules",
        lambda: (
            "if get_temp(RULE_RAW_FCU) == 23.0 and "
            "get_fcu_temp(RULE_RAW_FCU) == 20.0:\n"
            "    set_fan_speed(RULE_RAW_FCU, 2)\n"
        ),
    )

    assert (
        rules_engine.rules_results(conn, when=now)
        == f"Device {fcu_id} speed set to 2"
    )


def _connect_test_db():
    db_path = os.environ["TEST_DB_NAME"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def test_get_rooms_returns_room_models(test_database_conn):
    conn = test_database_conn
    _clear_devices(conn)

    db.create_room(conn, Room(room_name="Hickory"))

    rooms = db.get_rooms(conn)
    assert len(rooms) == 1
    assert isinstance(rooms[0], Room)
    assert rooms[0].room_name == "Hickory"


def test_rooms_api_round_trips_map_and_device_assignment(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    _, device_id, _ = test_database_conn_with_test_data
    room_payload = {
        "room_name": "Hickory",
        "map": {
            "polygon": [
                {"x": 10, "y": 20},
                {"x": 30, "y": 20},
                {"x": 20, "y": 40},
            ],
            "color": "#4f9d69",
        },
    }

    create_response = flask_test_client.post("/api/v1/rooms", json=room_payload)
    assert create_response.status_code == 201
    room = create_response.json
    assert room["room_name"] == "Hickory"
    assert room["map"] == room_payload["map"]

    updated_room = {**room, "map": {**room_payload["map"], "color": "#3366cc"}}
    patch_response = flask_test_client.patch(
        f"/api/v1/rooms/{room['room_id']}",
        json=updated_room,
    )
    assert patch_response.status_code == 200
    assert patch_response.json["map"]["color"] == "#3366cc"

    assign_response = flask_test_client.post(
        "/api/v1/update_device_room",
        json={"device_id": device_id, "room_id": room["room_id"]},
    )
    assert assign_response.status_code == 200

    status_response = flask_test_client.get("/api/v1/status")
    assigned = next(
        device
        for device in status_response.json["devices"]
        if device["device_id"] == device_id
    )
    assert assigned["room_id"] == room["room_id"]
    assert assigned["room_name"] == "Hickory"


def test_room_omits_none_values_and_updates_only_supplied_fields(flask_test_client):
    create_response = flask_test_client.post(
        "/api/v1/rooms",
        json={"room_name": "Mapless"},
    )
    assert create_response.status_code == 201
    room = create_response.json
    assert room["room_name"] == "Mapless"
    assert "map" not in room

    patch_response = flask_test_client.patch(
        f"/api/v1/rooms/{room['room_id']}",
        json={"map": {"color": "#123456"}},
    )
    assert patch_response.status_code == 200
    assert patch_response.json["room_name"] == "Mapless"
    assert patch_response.json["map"] == {"color": "#123456"}

    no_op_response = flask_test_client.patch(
        f"/api/v1/rooms/{room['room_id']}",
        json={},
    )
    assert no_op_response.status_code == 200
    assert no_op_response.json == patch_response.json

    invalid_create_response = flask_test_client.post(
        "/api/v1/rooms",
        json={"room_name": "Bad Color", "map": {"color": "blue"}},
    )
    assert invalid_create_response.status_code == 400
    assert invalid_create_response.json["error"] == "validation error"
    assert isinstance(invalid_create_response.json["details"], list)

    invalid_patch_response = flask_test_client.patch(
        f"/api/v1/rooms/{room['room_id']}",
        json={"map": {"color": "blue"}},
    )
    assert invalid_patch_response.status_code == 400
    assert invalid_patch_response.json["error"] == "validation error"
    assert isinstance(invalid_patch_response.json["details"], list)

    missing_name_response = flask_test_client.post(
        "/api/v1/rooms",
        json={"map": {"color": "#abcdef"}},
    )
    assert missing_name_response.status_code == 400
    assert missing_name_response.json["error"] == "room_name is required"


def test_fcu_temp_source_api_persists_multiplier_and_logs_old_new_values(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    with closing(_connect_test_db()) as conn:
        _, fcu_id, _ = test_database_conn_with_test_data
        now = int(time.time())
        source_id = _device(
            conn, TempDeviceSpec(name="Desk Sensor", temp10x=255, logtime=now - 30)
        )

    first = flask_test_client.post(
        "/api/v1/fcu_temp_source",
        json={
            "fcu_device_id": fcu_id,
            "source_device_id": source_id,
            "multiplier": 1.5,
        },
    )
    assert first.status_code == 200

    second = flask_test_client.post(
        "/api/v1/fcu_temp_source",
        json={
            "fcu_device_id": fcu_id,
            "source_device_id": source_id,
            "multiplier": 0.75,
        },
    )
    assert second.status_code == 200
    source = next(
        item for item in second.json["sources"] if item["source_device_id"] == source_id
    )
    assert source["multiplier"] == 0.75
    assert source["included"] is True

    logs = flask_test_client.get("/api/v1/logs").json["data"]
    multiplier_log = next(
        log
        for log in logs
        if log["current_values"] == "1.5" and log["new_value"] == "0.75"
    )
    assert "calculated temp multiplier" in multiplier_log["comment"]


def test_fcu_temp_sources_api_returns_default_weights(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    with closing(_connect_test_db()) as conn:
        _, fcu_id, _ = test_database_conn_with_test_data
        now = int(time.time())
        conn.execute(
            """
            INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (fcu_id, now - 30, 60, 240, json.dumps(_fcu_status())),
        )
        source_id = _device(
            conn,
            TempDeviceSpec(name="API Default Sensor", temp10x=255, logtime=now - 30),
        )
        conn.commit()

    response = flask_test_client.get(f"/api/v1/fcu_temp_sources?fcu_device_id={fcu_id}")

    assert response.status_code == 200
    assert response.json["fcu_device_id"] == fcu_id
    assert response.json["stale_seconds"] == TEMP_SOURCE_STALE_SECONDS
    by_id = {source["source_device_id"]: source for source in response.json["sources"]}
    assert by_id[fcu_id]["multiplier"] == 1.0
    assert by_id[fcu_id]["included"] is True
    assert by_id[fcu_id]["is_fcu_self"] is True
    assert by_id[source_id]["multiplier"] == 0.0
    assert by_id[source_id]["included"] is False

    with closing(_connect_test_db()) as conn:
        rows = conn.execute(
            """
            SELECT source_device_id, multiplier
            FROM fcu_temp_sources
            WHERE fcu_device_id=?
            """,
            (fcu_id,),
        ).fetchall()
    assert rows == []


def test_fcu_temp_sources_api_handles_fractional_source_age(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    with closing(_connect_test_db()) as conn:
        _, fcu_id, _ = test_database_conn_with_test_data
        conn.execute("DELETE FROM fcu_temp_sources WHERE fcu_device_id=?", (fcu_id,))
        conn.execute(
            """
            INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (fcu_id, time.time() - 112.75, 0.5, 240, json.dumps(_fcu_status())),
        )
        conn.commit()

    response = flask_test_client.get(f"/api/v1/fcu_temp_sources?fcu_device_id={fcu_id}")

    assert response.status_code == 200
    source = next(
        item for item in response.json["sources"] if item["source_device_id"] == fcu_id
    )
    assert isinstance(source["age_seconds"], int)
    assert source["multiplier"] == 1.0


def test_fcu_temp_source_api_persists_zero_fcu_override_and_logs_default_old_value(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    _, fcu_id, _ = test_database_conn_with_test_data

    response = flask_test_client.post(
        "/api/v1/fcu_temp_source",
        json={
            "fcu_device_id": fcu_id,
            "source_device_id": fcu_id,
            "multiplier": 0.0,
        },
    )

    assert response.status_code == 200
    by_id = {source["source_device_id"]: source for source in response.json["sources"]}
    assert by_id[fcu_id]["multiplier"] == 0.0
    assert by_id[fcu_id]["included"] is False

    with closing(_connect_test_db()) as conn:
        row = conn.execute(
            """
            SELECT multiplier
            FROM fcu_temp_sources
            WHERE fcu_device_id=? AND source_device_id=?
            """,
            (fcu_id, fcu_id),
        ).fetchone()
    assert row["multiplier"] == 0.0

    logs = flask_test_client.get("/api/v1/logs").json["data"]
    multiplier_log = next(
        log
        for log in logs
        if log["current_values"] == "1.0" and log["new_value"] == "0.0"
    )
    assert "calculated temp multiplier" in multiplier_log["comment"]


def test_fcu_temp_source_api_rejects_missing_and_unknown_devices(flask_test_client):
    missing = flask_test_client.get("/api/v1/fcu_temp_sources")
    assert missing.status_code == 400

    unknown_fcu = flask_test_client.get("/api/v1/fcu_temp_sources?fcu_device_id=999999")
    assert unknown_fcu.status_code == 404

    unknown_source = flask_test_client.post(
        "/api/v1/fcu_temp_source",
        json={
            "fcu_device_id": 999999,
            "source_device_id": 999998,
            "multiplier": 1.0,
        },
    )
    assert unknown_source.status_code == 404


def test_calculated_temperature_series_uses_source_history_and_staleness(
    test_database_conn,
):
    conn = test_database_conn
    _clear_devices(conn)
    base = 1_700_000_000

    fcu_id = db.get_or_create_device_id(conn, "Series FCU", use_cache=False)
    sensor_id = db.get_or_create_device_id(conn, "Series Wall Sensor", use_cache=False)
    _insert_temp_row(
        conn,
        TempRowSpec(
            device_id=fcu_id,
            logtime=base + 100,
            temp10x=200,
            status=_fcu_status(),
        ),
    )
    _insert_temp_row(
        conn,
        TempRowSpec(
            device_id=fcu_id,
            logtime=base + 200,
            temp10x=220,
            status=_fcu_status(),
        ),
    )
    _insert_temp_row(
        conn,
        TempRowSpec(
            device_id=fcu_id,
            logtime=base + 900,
            temp10x=240,
            status=_fcu_status(),
        ),
    )
    _insert_temp_row(
        conn,
        TempRowSpec(
            device_id=sensor_id,
            logtime=base + 50,
            temp10x=300,
            duration=100,
        ),
    )
    _insert_temp_row(
        conn,
        TempRowSpec(
            device_id=sensor_id,
            logtime=base + 180,
            temp10x=260,
        ),
    )
    conn.executemany(
        """
        INSERT INTO fcu_temp_sources
            (fcu_device_id, source_device_id, multiplier, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        [(fcu_id, fcu_id, 1.0, base), (fcu_id, sensor_id, 1.0, base)],
    )
    conn.commit()

    with app.test_request_context(
        f"/api/v1/temperature?start={base + 100}&end={base + 900}"
    ):
        series = db.get_calculated_temperature_series(conn, [fcu_id])

    assert series == [
        {
            "device_id": fcu_id,
            "name": "Series FCU",
            "data": [
                [base + 100, 25.0],
                [base + 200, 24.0],
                [base + 900, 24.0],
            ],
        }
    ]


def test_temperature_api_calculated_mode_returns_only_fcus(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    with closing(_connect_test_db()) as conn:
        _, fcu_id, _ = test_database_conn_with_test_data
        now = int(time.time())
        sensor_id = _device(
            conn, TempDeviceSpec(name="Center Sensor", temp10x=260, logtime=now - 30)
        )
        conn.executemany(
            """
            INSERT INTO fcu_temp_sources
                (fcu_device_id, source_device_id, multiplier, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            [(fcu_id, fcu_id, 1.0, now), (fcu_id, sensor_id, 1.0, now)],
        )
        conn.commit()

    raw = flask_test_client.get("/api/v1/temperature?mode=raw")
    assert raw.status_code == 200
    assert sensor_id in {series["device_id"] for series in raw.json["series"]}

    calculated = flask_test_client.get("/api/v1/temperature?mode=calculated")
    assert calculated.status_code == 200
    calculated_ids = {series["device_id"] for series in calculated.json["series"]}
    assert fcu_id in calculated_ids
    assert sensor_id not in calculated_ids

    invalid = flask_test_client.get("/api/v1/temperature?mode=bogus")
    assert invalid.status_code == 400


def test_temperature_api_calculated_mode_uses_default_fcu_weight(
    flask_test_client, test_database_conn_with_test_data
):  # noqa: F811
    _, fcu_id, _ = test_database_conn_with_test_data

    calculated = flask_test_client.get(
        f"/api/v1/temperature?mode=calculated&device_ids={fcu_id}"
    )
    assert calculated.status_code == 200
    assert [series["device_id"] for series in calculated.json["series"]] == [fcu_id]
    assert all(
        point[1] == 24.0 for point in calculated.json["series"][0]["data"]
    )
