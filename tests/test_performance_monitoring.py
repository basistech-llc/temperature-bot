"""Substantive SQLite, timing, parser, and loopback probe tests."""

import asyncio
import logging
import socket
import time

import pytest
import websockets

from app import ae200
from app import performance_monitoring
from bin import performance_monitor as performance_monitor_cli


LINUX_PING_OUTPUT = """PING ae200 (192.0.2.10) 56(84) bytes of data.
64 bytes from 192.0.2.10: icmp_seq=1 ttl=63 time=12.4 ms
64 bytes from 192.0.2.10: icmp_seq=2 ttl=63 time=14.8 ms
64 bytes from 192.0.2.10: icmp_seq=3 ttl=63 time=13.1 ms

--- ae200 ping statistics ---
3 packets transmitted, 3 received, 0% packet loss, time 2003ms
"""

MACOS_PING_WITH_LOSS_OUTPUT = """PING ae200 (192.0.2.10): 56 data bytes
64 bytes from 192.0.2.10: icmp_seq=0 ttl=63 time=21.250 ms
64 bytes from 192.0.2.10: icmp_seq=2 ttl=63 time=19.750 ms

--- ae200 ping statistics ---
3 packets transmitted, 2 packets received, 33.3% packet loss
"""


def _sample(observed_at_ms: int, *, operation: str = "get_devices"):
    return performance_monitoring.PerformanceSample(
        observed_at_ms=observed_at_ms,
        instance_id="test",
        client_id="pytest",
        sample_type=performance_monitoring.SAMPLE_TYPE_AE200,
        operation=operation,
        target_host="ae200.example",
        target_port=80,
        lock_wait_ms=1.25,
        connect_ms=2.5,
        response_ms=3.75,
        total_ms=8.0,
        success=True,
        outcome="ok",
    )


def test_ping_parser_handles_linux_and_macos_loss():
    """Individual replies determine median even when one macOS packet is lost."""
    linux = performance_monitoring.parse_ping_output(LINUX_PING_OUTPUT)
    macos = performance_monitoring.parse_ping_output(MACOS_PING_WITH_LOSS_OUTPUT)

    assert linux.model_dump() == {
        "minimum_ms": 12.4,
        "median_ms": 13.1,
        "maximum_ms": 14.8,
        "packet_loss_pct": 0.0,
        "replies": 3,
    }
    assert macos.minimum_ms == 19.75
    assert macos.median_ms == 20.5
    assert macos.maximum_ms == 21.25
    assert macos.packet_loss_pct == 33.3
    assert macos.replies == 2


def test_tcp_reject_probe_treats_loopback_refusal_as_reachable():
    """A closed local port produces the probe's expected successful outcome."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    closed_port = listener.getsockname()[1]
    listener.close()

    sample = performance_monitoring.probe_tcp_reject(
        "localhost", closed_port, resolved_ip="127.0.0.1"
    )

    assert sample.success is True
    assert sample.outcome == "refused"
    assert sample.connect_ms is not None
    assert sample.total_ms >= sample.connect_ms


def test_dns_address_selection_prefers_ipv4_for_portable_ping():
    """An IPv4 result wins even when DNS returns IPv6 first."""
    addresses = [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::10", 0, 0, 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.10", 0)),
    ]

    assert performance_monitoring.preferred_stream_address(addresses) == "192.0.2.10"


def test_best_effort_record_does_not_wait_for_sqlite_writer(
    test_database_conn, caplog
):
    """Inline telemetry abandons a locked database without delaying AE-200 work."""
    test_database_conn.execute("BEGIN EXCLUSIVE")
    started = time.perf_counter()
    with caplog.at_level(logging.WARNING):
        performance_monitoring.record_sample_best_effort(_sample(9_000))
    elapsed = time.perf_counter() - started
    test_database_conn.rollback()

    assert elapsed < 0.5
    assert "database is locked" in caplog.text
    assert (
        test_database_conn.execute(
            "SELECT count(*) FROM performance_samples WHERE observed_at_ms = 9000"
        ).fetchone()[0]
        == 0
    )


def test_performance_samples_persist_filter_and_expire(test_database_conn):
    """Persistence keeps filters precise and retention deletes only old rows."""
    performance_monitoring.insert_sample(test_database_conn, _sample(1_000))
    performance_monitoring.insert_sample(
        test_database_conn, _sample(2_000, operation="get_device_info")
    )
    performance_monitoring.insert_sample(
        test_database_conn,
        performance_monitoring.PerformanceSample(
            observed_at_ms=2_500,
            instance_id="other",
            client_id="probe",
            sample_type=performance_monitoring.SAMPLE_TYPE_TCP_REJECT,
            operation=performance_monitoring.OPERATION_REJECT,
            target_host="ae200.example",
            target_port=1,
            connect_ms=4,
            total_ms=4,
            success=True,
            outcome="refused",
        ),
    )
    test_database_conn.commit()

    rows = performance_monitoring.fetch_samples(
        test_database_conn,
        performance_monitoring.PerformanceQuery(
            start_ms=1_500,
            end_ms=3_000,
            instance_id="test",
            operation="get_device_info",
        ),
    )
    assert len(rows) == 1
    assert rows[0].observed_at_ms == 2_000

    deleted = performance_monitoring.delete_expired_samples(
        test_database_conn, now_ms=3_000, retention_days=1
    )
    assert deleted == 0
    deleted = performance_monitoring.delete_expired_samples(
        test_database_conn,
        now_ms=2 * 24 * 60 * 60 * 1000,
        retention_days=1,
    )
    assert deleted == 3


def test_async_runner_records_success_and_original_failure(
    test_database_conn, monkeypatch, tmp_path
):
    """Instrumentation records both outcomes without replacing exceptions."""
    test_database_conn.commit()
    monkeypatch.setattr(ae200, "AE200_COMMAND_LOCK_PATH", str(tmp_path / "ae200.lock"))
    runner = ae200.AsyncRunner()

    async def succeed():
        await asyncio.sleep(0)
        return "done"

    success = _sample(10_000)
    success.success = False
    success.outcome = "pending"
    assert runner.run_async_safely(succeed(), sample=success) == "done"

    async def fail():
        await asyncio.sleep(0)
        raise ValueError("controller rejected payload")

    failure = _sample(11_000, operation="set")
    with pytest.raises(ValueError, match="controller rejected payload"):
        runner.run_async_safely(fail(), sample=failure)

    rows = test_database_conn.execute(
        """
        SELECT observed_at_ms, success, outcome, error_type, lock_wait_ms
        FROM performance_samples
        WHERE observed_at_ms IN (10000, 11000)
        ORDER BY observed_at_ms
        """
    ).fetchall()
    assert [tuple(row[:4]) for row in rows] == [
        (10_000, 1, "ok", None),
        (11_000, 0, "error", "ValueError"),
    ]
    assert all(row[4] >= 0 for row in rows)


def test_ae200_exchange_times_real_local_websocket(monkeypatch):
    """Phase timing wraps an actual WebSocket upgrade and XML round trip."""
    response_xml = """<Packet><DatabaseManager><ControlGroup><MnetList>
    <MnetRecord Group="10" GroupNameWeb="Office"/>
    </MnetList></ControlGroup></DatabaseManager></Packet>"""

    async def exercise():
        async def handler(websocket):
            assert await websocket.recv() == ae200.getUnitsPayload
            await websocket.send(response_xml)

        async with websockets.serve(
            handler, "127.0.0.1", 0, subprotocols=["b_xmlproc"]
        ) as server:
            port = server.sockets[0].getsockname()[1]
            controller = ae200.AE200Functions(f"127.0.0.1:{port}")
            sample = performance_monitoring.new_ae200_sample(
                performance_monitoring.OPERATION_GET_DEVICES,
                controller.address,
            )
            devices = await controller.getDevicesAsync(sample)
            return devices, sample

    monkeypatch.setattr(ae200, "AE200_SIMULATOR", False)
    devices, sample = asyncio.run(exercise())

    assert devices == [{"id": "10", "name": "Office"}]
    assert sample.connect_ms is not None
    assert sample.response_ms is not None
    assert sample.close_ms is not None
    assert sample.response_bytes == len(response_xml.encode("utf-8"))


def test_performance_api_and_page(flask_test_client, test_database_conn):
    """The page is linked to a bounded API that returns persisted samples."""
    performance_monitoring.insert_sample(test_database_conn, _sample(20_000))
    performance_monitoring.insert_sample(test_database_conn, _sample(20_001))
    test_database_conn.commit()

    page = flask_test_client.get("/performance-monitoring")
    response = flask_test_client.get(
        "/api/v1/performance_samples?start_ms=19000&end_ms=21000&limit=1"
    )

    assert page.status_code == 200
    assert b"Performance Monitoring" in page.data
    assert b"performance_monitoring.js" in page.data
    assert response.status_code == 200
    assert response.get_json()["samples"][0]["operation"] == "get_devices"
    assert response.get_json()["truncated"] is True
    invalid = flask_test_client.get(
        "/api/v1/performance_samples?start_ms=21000&end_ms=19000"
    )
    assert invalid.status_code == 400
    malformed = flask_test_client.get(
        "/api/v1/performance_samples?start_ms=not-a-number"
    )
    assert malformed.status_code == 400


def test_performance_probe_cli_refuses_unscheduled_loop_mode(monkeypatch):
    """The probe cannot accidentally become an unsupervised internal loop."""
    monkeypatch.setattr("sys.argv", ["performance_monitor"])
    with pytest.raises(SystemExit, match="--once is required"):
        performance_monitor_cli.main()
