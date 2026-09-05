"""Substantive tests for shared room metric source selection."""

import json

from pydantic import BaseModel

from app import db
from app.models import Room
from app.room_metrics import (
    RoomMetric,
    RoomMetricExclusionReason,
    select_room_metric_sources,
)


class ReadingSpec(BaseModel):
    """One persisted reading used by the room-selection test."""

    logtime: float
    temp10x: int | None
    status: object
    duration: float = 0


def _device(conn, name: str, device_type: str, room_id: int | None) -> int:
    cursor = conn.execute(
        """
        INSERT INTO devices (device_name, device_type, room_id)
        VALUES (?, ?, ?)
        """,
        (name, device_type, room_id),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def _reading(
    conn,
    device_id: int,
    reading: ReadingSpec,
) -> None:
    status_json = (
        reading.status
        if isinstance(reading.status, str)
        else json.dumps(reading.status)
    )
    conn.execute(
        """
        INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            device_id,
            reading.logtime,
            reading.duration,
            reading.temp10x,
            status_json,
        ),
    )


def _exclusions(selection) -> dict[int, RoomMetricExclusionReason]:
    return {item.device_id: item.reason for item in selection.exclusions}


def test_shared_room_selection_handles_membership_freshness_and_payload_shapes(
    test_database_conn,
):
    conn = test_database_conn
    at_time = 10_000
    room_id = db.create_room(conn, Room(room_name="Hickory")).room_id
    other_room_id = db.create_room(conn, Room(room_name="Kitchen")).room_id
    assert room_id is not None
    assert other_room_id is not None

    scalar_id = _device(conn, "Scalar Sensor", "SENSOR", room_id)
    dict_id = _device(conn, "Airthings Sensor", "SENSOR", room_id)
    boundary_id = _device(conn, "Boundary Sensor", "SENSOR", room_id)
    stale_id = _device(conn, "Stale Sensor", "SENSOR", room_id)
    other_room_device_id = _device(conn, "Kitchen Sensor", "SENSOR", other_room_id)
    erv_id = _device(conn, "ERV 1", "ERV", room_id)
    internal_id = _device(conn, "rules_engine", "INTERNAL", room_id)
    missing_id = _device(conn, "Missing Humidity", "SENSOR", room_id)
    malformed_id = _device(conn, "Malformed Status", "SENSOR", room_id)

    _reading(
        conn,
        scalar_id,
        ReadingSpec(logtime=9_900, temp10x=200, status={"humidity": 35}),
    )
    _reading(
        conn,
        scalar_id,
        ReadingSpec(logtime=9_950, temp10x=210, status={"humidity": 40}),
    )
    _reading(
        conn,
        scalar_id,
        ReadingSpec(logtime=10_100, temp10x=999, status={"humidity": 99}),
    )
    _reading(
        conn,
        dict_id,
        ReadingSpec(
            logtime=9_900,
            temp10x=230,
            status={"humidity": {"value": 50.5, "unit": "%"}},
        ),
    )
    _reading(
        conn,
        boundary_id,
        ReadingSpec(
            logtime=9_400,
            temp10x=240,
            status={"attributes": {"humidity": 60}},
        ),
    )
    _reading(
        conn,
        stale_id,
        ReadingSpec(logtime=9_399, temp10x=300, status={"humidity": 80}),
    )
    for device_id in (other_room_device_id, erv_id, internal_id):
        _reading(
            conn,
            device_id,
            ReadingSpec(logtime=9_990, temp10x=250, status={"humidity": 45}),
        )
    _reading(
        conn,
        missing_id,
        ReadingSpec(logtime=9_990, temp10x=None, status={}),
    )
    _reading(
        conn,
        malformed_id,
        ReadingSpec(logtime=9_990, temp10x=260, status="not-json"),
    )
    conn.commit()

    snapshots = db.fetch_latest_room_metric_snapshots(conn, at_time=at_time)
    current_snapshots = db.fetch_latest_room_metric_snapshots(conn)
    current_scalar = next(
        item for item in current_snapshots if item.device_id == scalar_id
    )
    assert current_scalar.temp10x == 999

    temperature = select_room_metric_sources(
        snapshots,
        room_id=room_id,
        metric=RoomMetric.TEMPERATURE,
        at_time=at_time,
    )
    humidity = select_room_metric_sources(
        snapshots,
        room_id=room_id,
        metric=RoomMetric.HUMIDITY,
        at_time=at_time,
    )

    assert {source.device_id: source.value for source in temperature.sources} == {
        dict_id: 23.0,
        boundary_id: 24.0,
        malformed_id: 26.0,
        scalar_id: 21.0,
    }
    assert {source.device_id: source.value for source in humidity.sources} == {
        dict_id: 50.5,
        boundary_id: 60.0,
        scalar_id: 40.0,
    }
    assert next(
        source for source in temperature.sources if source.device_id == boundary_id
    ).age_seconds == 600

    temperature_exclusions = _exclusions(temperature)
    humidity_exclusions = _exclusions(humidity)
    assert temperature_exclusions[stale_id] == RoomMetricExclusionReason.STALE
    assert temperature_exclusions[other_room_device_id] == RoomMetricExclusionReason.ROOM
    assert temperature_exclusions[erv_id] == RoomMetricExclusionReason.DEVICE_TYPE
    assert temperature_exclusions[internal_id] == RoomMetricExclusionReason.DEVICE_TYPE
    assert (
        temperature_exclusions[missing_id]
        == RoomMetricExclusionReason.MISSING_METRIC
    )
    assert humidity_exclusions[malformed_id] == RoomMetricExclusionReason.MISSING_METRIC
    assert humidity_exclusions[missing_id] == RoomMetricExclusionReason.MISSING_METRIC


def test_latest_snapshot_uses_log_id_to_break_timestamp_ties(test_database_conn):
    conn = test_database_conn
    device_id = _device(conn, "Tied Sensor", "SENSOR", None)
    _reading(
        conn,
        device_id,
        ReadingSpec(logtime=1_000, temp10x=200, status={"humidity": 40}),
    )
    _reading(
        conn,
        device_id,
        ReadingSpec(logtime=1_000, temp10x=210, status={"humidity": 41}),
    )
    _reading(
        conn,
        device_id,
        ReadingSpec(logtime=1_001, temp10x=220, status={"humidity": 42}),
    )
    conn.commit()

    snapshot = db.fetch_latest_room_metric_snapshots(conn, at_time=1_000)[0]

    assert snapshot.device_id == device_id
    assert snapshot.temp10x == 210
    assert snapshot.status is not None
    assert snapshot.status.humidity == 41


def test_latest_snapshot_query_uses_bounded_composite_index(test_database_conn):
    plan = test_database_conn.execute(
        f"EXPLAIN QUERY PLAN {db.LATEST_ROOM_METRIC_SNAPSHOTS_SQL}",
        (1_000,),
    ).fetchall()
    details = "\n".join(str(row[3]) for row in plan)

    assert "idx_devlog_device_logtime_log_id" in details
    assert "(device_id=? AND logtime<?)" in details
    assert "CO-ROUTINE" not in details
