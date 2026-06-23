"""
test for db.py
"""

import logging
import json

from app import db
from app import aq_metrics
from app.main import app
from bin import runner


logger = logging.getLogger(__name__)

def test_temperature_insert(test_database_conn_with_test_data):
    conn = test_database_conn_with_test_data[0]

    # Clear out the devlog
    c = conn.cursor()
    c.execute("delete from devlog")
    conn.commit()

    db.insert_devlog_entry(conn, device_name="devtest1", temp=20, logtime=100)
    db.insert_devlog_entry(conn, device_name="devtest1", temp=20, logtime=101) # extends first measurement by 1 second to 2 seconds
    db.insert_devlog_entry(conn, device_name="devtest1", temp=20, logtime=112) # extends first measurement by another 11 seconds to 13 seconds

    db.insert_devlog_entry(conn, device_name="devtest2", temp=20, logtime=100)
    db.insert_devlog_entry(conn, device_name="devtest2", temp=21, logtime=111) # new measurement. We now have two measurements with 1 second each.
    db.insert_devlog_entry(conn, device_name="devtest2", temp=22, logtime=112) # new measurement. We have no idea when when the measurement changes.
                                                                      # We have 3 measurements, 1 second each

    dev1_id = db.get_or_create_device_id(conn, "devtest1")
    dev2_id = db.get_or_create_device_id(conn, "devtest2")
    assert dev1_id != dev2_id

    c = conn.cursor()
    c.execute("SELECT *,dn.device_name as device_name from devlog d1 INNER JOIN (select device_id,MAX(logtime) as max_logtime from devlog group by device_id) as d2 on d1.device_id = d2.device_id and d1.logtime = d2.max_logtime INNER JOIN devices dn on d1.device_id = dn.device_id")
    rows = c.fetchall()
    assert len(rows)==2
    assert rows[0]['device_name'] == 'devtest1'
    assert rows[0]['temp10x'] == 200
    assert rows[0]['logtime'] == 100
    assert rows[0]['duration'] == 13
    devtest1_id = rows[0]['device_id']

    assert rows[1]['device_name'] == 'devtest2'
    assert rows[1]['temp10x'] == 220
    assert rows[1]['logtime'] == 112
    assert rows[1]['duration'] == 1
    devtest2_id = rows[1]['device_id']

    # make sure status_json behaves as expected
    db.insert_devlog_entry(conn, device_name="complex1", statusdict={'name':'foo', 'val':'bar'}, logtime=100)
    db.insert_devlog_entry(conn, device_name="complex1", statusdict={'name':'foo', 'val':'bar2'}, logtime=101)
    db.insert_devlog_entry(conn, device_name="complex1", statusdict={'name':'foo', 'val':'bar2'}, logtime=102)
    c.execute("SELECT * from devlog where device_id=(select device_id from devices where device_name='complex1') order by logtime DESC limit 1")
    rows = c.fetchall()
    assert len(rows)==1
    assert json.loads(rows[0]['status_json']) == {'name':'foo', 'val' : 'bar2'}

    # finally, check to see if our combining code broadly works
    logging.debug("devtest1_id=%s",devtest1_id)
    runner.combine_temp_measurements(conn,100,150,50)
    c.execute("SELECT * from devlog where device_id=?",(devtest1_id,))
    rows = c.fetchall()
    assert len(rows)==1
    assert rows[0]['logtime']==100
    assert rows[0]['duration']==50
    assert rows[0]['temp10x']==200 # temperature never changed from 20

    c.execute("SELECT * from devlog where device_id=?",(devtest2_id,))
    rows = c.fetchall()
    assert len(rows)==1
    assert rows[0]['logtime']==100
    assert rows[0]['duration']==50
    assert rows[0]['temp10x']==210 # 1 seconds at 20, 1 second at 21, 1 second at 22


def test_insert_devlog_entry_normalizes_float_logtime(
    test_database_conn_with_test_data,
):
    conn = test_database_conn_with_test_data[0]

    db.insert_devlog_entry(
        conn,
        device_name="float-logtime-device",
        temp=20,
        logtime=100.75,
        force=True,
    )

    device_id = db.get_or_create_device_id(conn, "float-logtime-device")
    row = conn.execute(
        "SELECT logtime FROM devlog WHERE device_id=? ORDER BY logtime DESC LIMIT 1",
        (device_id,),
    ).fetchone()
    assert row["logtime"] == 100

    status = db.get_device_status(conn)
    device = next(item for item in status if item["device_id"] == device_id)
    assert device["logtime"] == 100


def test_insert_devlog_entry_extends_legacy_float_logtime_with_integer_duration(
    test_database_conn_with_test_data,
):
    conn = test_database_conn_with_test_data[0]
    c = conn.cursor()
    c.execute("DELETE FROM devlog")
    c.execute("DELETE FROM devices")
    conn.commit()

    device_id = db.get_or_create_device_id(conn, "legacy-float-logtime-device")
    c.execute(
        "INSERT INTO devlog (device_id, logtime, duration, temp10x) VALUES (?, ?, ?, ?)",
        (device_id, 100.75, 1.25, 200),
    )
    conn.commit()

    db.insert_devlog_entry(
        conn,
        device_name="legacy-float-logtime-device",
        temp=20,
        logtime=105.9,
    )

    row = conn.execute(
        "SELECT duration FROM devlog WHERE device_id=? ORDER BY logtime DESC LIMIT 1",
        (device_id,),
    ).fetchone()
    assert row["duration"] == 6


def test_time_series_builders_normalize_legacy_float_logtime(
    test_database_conn_with_test_data,
):
    conn = test_database_conn_with_test_data[0]
    c = conn.cursor()
    c.execute("DELETE FROM devlog")
    c.execute("DELETE FROM devices")
    conn.commit()

    device_id = db.get_or_create_device_id(conn, "Airthings Legacy")
    payload = {
        "co2": {"value": 600, "unit": "ppm"},
        "illuminance": 12.5,
    }
    c.execute(
        "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
        (device_id, 1000.75, 61.25, 219, json.dumps(payload)),
    )
    conn.commit()

    with app.test_request_context():
        temp_series = db.get_temperature_series(conn, [device_id])
        metric_series = db.get_device_metric_series(conn, "co2", [device_id])
        lighting_series = db.get_lighting_series(conn, [device_id])

    assert temp_series[0]["data"] == [[1000, 21.9]]
    assert metric_series[0]["data"] == [[1000, 600.0]]
    assert lighting_series[0]["data"] == [[1000, 12.5]]


def test_get_lighting_series_uses_status_json_illuminance(
    test_database_conn_with_test_data,
):  # noqa: F811
    """get_lighting_series extracts illuminance from status_json and returns non-empty series."""
    conn = test_database_conn_with_test_data[0]
    # Clear devlog and devices to control test data
    c = conn.cursor()
    c.execute("DELETE FROM devlog")
    c.execute("DELETE FROM devices")
    conn.commit()

    # Create a device and a few devlog rows with status_json containing illuminance
    device_id = db.get_or_create_device_id(conn, "Lighting Test Device")
    rows = [
      (device_id, 1000, '{"illuminance": 10}'),
      (device_id, 1010, '{"attributes": {"illuminance": 12.5}}'),
    ]
    for logtime, status_json in [(t, s) for (_, t, s) in rows]:
        c.execute(
            "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
            (device_id, logtime, 1, None, status_json),
        )
    conn.commit()

    with app.test_request_context():
        series = db.get_lighting_series(conn, [device_id])
    assert series, "expected at least one lighting series"
    assert series[0]["name"] == "Lighting Test Device"
    datapoints = series[0]["data"]
    assert len(datapoints) == 2
    # Values should be numeric and match the JSON payloads
    values = [v for (_, v) in datapoints]
    assert 10.0 in values
    assert 12.5 in values


def test_get_device_metric_series_airthings_dict(test_database_conn_with_test_data):
    """Airthings-style status_json stores each metric as {value, unit}; the helper must unwrap."""
    conn = test_database_conn_with_test_data[0]
    c = conn.cursor()
    c.execute("DELETE FROM devlog")
    c.execute("DELETE FROM devices")
    conn.commit()

    device_id = db.get_or_create_device_id(conn, "Airthings Office")
    samples = [
        (1000, {"co2": {"value": 600, "unit": "ppm"}, "humidity": {"value": 45.5, "unit": "%"}}),
        (1010, {"co2": {"value": 650, "unit": "ppm"}, "humidity": {"value": 46.0, "unit": "%"}}),
    ]
    for logtime, payload in samples:
        c.execute(
            "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
            (device_id, logtime, 1, None, json.dumps(payload)),
        )
    conn.commit()

    with app.test_request_context():
        co2_series = db.get_device_metric_series(conn, "co2", [device_id])
    assert co2_series, "expected co2 series"
    assert co2_series[0]["device_id"] == device_id
    values = [v for (_, v) in co2_series[0]["data"]]
    assert 600.0 in values and 650.0 in values

    with app.test_request_context():
        humidity_series = db.get_device_metric_series(conn, "humidity", [device_id])
    values = [v for (_, v) in humidity_series[0]["data"]]
    assert 45.5 in values and 46.0 in values


def test_get_device_metric_series_hubitat_scalar(test_database_conn_with_test_data):
    """Hubitat sensors store humidity as a top-level scalar or inside attributes."""
    conn = test_database_conn_with_test_data[0]
    c = conn.cursor()
    c.execute("DELETE FROM devlog")
    c.execute("DELETE FROM devices")
    conn.commit()

    device_id = db.get_or_create_device_id(conn, "Hubitat Sensor")
    samples = [
        (2000, {"humidity": 38}),
        (2010, {"attributes": {"humidity": 40.5}}),
    ]
    for logtime, payload in samples:
        c.execute(
            "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
            (device_id, logtime, 1, None, json.dumps(payload)),
        )
    conn.commit()

    with app.test_request_context():
        series = db.get_device_metric_series(conn, "humidity", [device_id])
    values = [v for (_, v) in series[0]["data"]]
    assert 38.0 in values and 40.5 in values


def test_coerce_metric_value_handles_malformed_input():
    """Non-numeric and empty-value inputs must produce None, not raise.

    Airthings payloads always have numeric values, but we parse whatever the
    device returned. A single malformed row should skip cleanly so the rest
    of the series still renders.
    """
    # Dict with missing or empty value key
    assert aq_metrics.coerce_metric_value({"value": None, "unit": "%"}) is None
    assert aq_metrics.coerce_metric_value({"value": "", "unit": "%"}) is None
    # Non-numeric scalars and non-numeric dict values
    assert aq_metrics.coerce_metric_value("n/a") is None
    assert aq_metrics.coerce_metric_value({"value": "n/a"}) is None
    # Happy paths still work alongside the error cases
    assert aq_metrics.coerce_metric_value({"value": 3.14}) == 3.14
    assert aq_metrics.coerce_metric_value(42) == 42.0


def test_get_device_metric_series_filters_by_device_ids(test_database_conn_with_test_data):
    """The device_ids filter must actually exclude other devices.

    The prior happy-path test passed every device's own id; this guards the
    branch that skips devices outside the filter list, which is relied on
    when a user clicks a single cell and we only want that one series.
    """
    conn = test_database_conn_with_test_data[0]
    c = conn.cursor()
    c.execute("DELETE FROM devlog")
    c.execute("DELETE FROM devices")
    conn.commit()

    keep_id = db.get_or_create_device_id(conn, "Keep Me")
    drop_id = db.get_or_create_device_id(conn, "Filter Me Out")
    for logtime, did in [(1000, keep_id), (1010, drop_id), (1020, keep_id)]:
        c.execute(
            "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
            (did, logtime, 1, None, json.dumps({"co2": {"value": 500}})),
        )
    conn.commit()

    with app.test_request_context():
        series = db.get_device_metric_series(conn, "co2", [keep_id])
    assert len(series) == 1
    assert series[0]["device_id"] == keep_id


def test_get_device_metric_series_skips_bad_json(test_database_conn_with_test_data):
    """A single row with unparseable status_json must not poison the whole series.

    Guards the except-JSONDecodeError branch. If a corrupt row ever lands in
    devlog, the chart should still render the surrounding good points.
    """
    conn = test_database_conn_with_test_data[0]
    c = conn.cursor()
    c.execute("DELETE FROM devlog")
    c.execute("DELETE FROM devices")
    conn.commit()

    device_id = db.get_or_create_device_id(conn, "Noisy Device")
    # Good, bad, good
    c.execute(
        "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
        (device_id, 1000, 1, None, json.dumps({"co2": {"value": 500}})),
    )
    c.execute(
        "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
        (device_id, 1010, 1, None, "{not valid json"),
    )
    c.execute(
        "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
        (device_id, 1020, 1, None, json.dumps({"co2": {"value": 550}})),
    )
    conn.commit()

    with app.test_request_context():
        series = db.get_device_metric_series(conn, "co2", [device_id])
    assert len(series) == 1
    values = [v for (_, v) in series[0]["data"]]
    assert values == [500.0, 550.0]


def test_get_device_metric_series_skips_missing(test_database_conn_with_test_data):
    """Rows without the requested metric are skipped; a device with zero samples is omitted."""
    conn = test_database_conn_with_test_data[0]
    c = conn.cursor()
    c.execute("DELETE FROM devlog")
    c.execute("DELETE FROM devices")
    conn.commit()

    device_id = db.get_or_create_device_id(conn, "No CO2 Device")
    c.execute(
        "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
        (device_id, 3000, 1, None, json.dumps({"humidity": 50})),
    )
    conn.commit()

    with app.test_request_context():
        series = db.get_device_metric_series(conn, "co2", [device_id])
    assert not series


def test_get_device_status_sets_aq_metric_flags(test_database_conn_with_test_data):
    """Per-metric has_<metric> flags should reflect the latest status_json contents."""
    conn = test_database_conn_with_test_data[0]
    c = conn.cursor()
    c.execute("DELETE FROM devlog")
    c.execute("DELETE FROM devices")
    conn.commit()

    airthings_id = db.get_or_create_device_id(conn, "Airthings Lab")
    hubitat_id = db.get_or_create_device_id(conn, "Hubitat Lab")

    airthings_payload = {
        "co2": {"value": 700, "unit": "ppm"},
        "humidity": {"value": 44, "unit": "%"},
        "voc": {"value": 120, "unit": "ppb"},
        "radonShortTermAvg": {"value": 30, "unit": "Bq/m3"},
        "pm25": {"value": 5, "unit": "ug/m3"},
        "pm1": {"value": 2, "unit": "ug/m3"},
        "pressure": {"value": 1013.2, "unit": "hPa"},
    }
    hubitat_payload = {"humidity": 42}

    c.execute(
        "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
        (airthings_id, 4000, 1, None, json.dumps(airthings_payload)),
    )
    c.execute(
        "INSERT INTO devlog (device_id, logtime, duration, temp10x, status_json) VALUES (?, ?, ?, ?, ?)",
        (hubitat_id, 4000, 1, None, json.dumps(hubitat_payload)),
    )
    conn.commit()

    with app.test_request_context():
        status = db.get_device_status(conn)
    by_id = {d["device_id"]: d for d in status}

    airthings = by_id[airthings_id]
    for metric in ("humidity", "co2", "voc", "radon", "pm25", "pm1", "pressure"):
        assert airthings[f"has_{metric}"] is True, metric

    hubitat = by_id[hubitat_id]
    assert hubitat["has_humidity"] is True
    for metric in ("co2", "voc", "radon", "pm25", "pm1", "pressure"):
        assert hubitat[f"has_{metric}"] is False, metric


def test_get_device_status_includes_ae200_device_id(test_database_conn):
    """Status rows should expose the configured AE-200 unit id."""
    device_id = db.update_devlog_map(
        test_database_conn,
        device_name="Broadway Status",
        ae200_device_id=10,
    )
    db.insert_devlog_entry(
        test_database_conn,
        device_id=device_id,
        temp=24,
        statusdict={"Drive": "ON", "FanSpeed": "LOW", "InletTemp": "24.0"},
    )

    with app.test_request_context():
        status = db.get_device_status(test_database_conn)

    row = next(item for item in status if item["device_id"] == device_id)
    assert row["ae200_device_id"] == 10
    assert row["device_type"] == "FCU"
    assert row["rules_enabled"] is True


def test_get_temperature_series_includes_device_id(test_database_conn_with_test_data):
    """get_temperature_series returns each series with device_id, name, and data."""
    conn = test_database_conn_with_test_data[0]
    device_id = test_database_conn_with_test_data[1]
    with app.test_request_context():
        series = db.get_temperature_series(conn, [device_id])
    assert series, "expected at least one temperature series"
    for s in series:
        assert "device_id" in s
        assert s["device_id"] == device_id
        assert "name" in s
        assert "data" in s
        assert isinstance(s["data"], list)
