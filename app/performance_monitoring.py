"""Persist and query AE-200 and network performance samples."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import socket
import sqlite3
import statistics
import subprocess
import sys
import time

from pydantic import BaseModel, Field

from .constants import DB_PATH, TEST_DB_NAME

logger = logging.getLogger(__name__)

PERFORMANCE_TABLE = "performance_samples"
PERFORMANCE_INSTANCE_ENV = "TEMPERATURE_BOT_INSTANCE"
PERFORMANCE_CLIENT_ENV = "PERFORMANCE_CLIENT_ID"
PERFORMANCE_EXPERIMENT_ENV = "PERFORMANCE_EXPERIMENT_ID"
PERFORMANCE_RETENTION_DAYS_ENV = "PERFORMANCE_RETENTION_DAYS"
AE200_REJECT_PORT_ENV = "AE200_REJECT_PORT"

SAMPLE_TYPE_AE200 = "ae200_request"
SAMPLE_TYPE_DNS = "dns"
SAMPLE_TYPE_ICMP = "icmp_ping"
SAMPLE_TYPE_TCP_REJECT = "tcp_reject"

OPERATION_GET_DEVICES = "get_devices"
OPERATION_GET_DEVICE_INFO = "get_device_info"
OPERATION_SET = "set"
OPERATION_RESOLVE = "resolve"
OPERATION_ECHO = "echo"
OPERATION_REJECT = "reject"

DEFAULT_REJECT_PORT = 1
DEFAULT_RETENTION_DAYS = 90
DEFAULT_QUERY_LIMIT = 50_000
MAX_QUERY_LIMIT = 100_000
MAX_ERROR_MESSAGE_LENGTH = 500
AE200_WEBSOCKET_PORT = 80
BEST_EFFORT_SQLITE_TIMEOUT_SECONDS = 0

PING_TIME_RE = re.compile(r"\btime[=<]([0-9]+(?:\.[0-9]+)?)\s*ms\b")
PACKET_LOSS_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)%\s+packet loss")


def default_instance_id() -> str:
    return os.getenv(PERFORMANCE_INSTANCE_ENV) or socket.gethostname()


def default_client_id() -> str:
    configured = os.getenv(PERFORMANCE_CLIENT_ENV)
    if configured:
        return configured
    return Path(sys.argv[0]).stem or "unknown"


def _default_experiment_id() -> str | None:
    return os.getenv(PERFORMANCE_EXPERIMENT_ENV) or None


def elapsed_ms(start_ns: int) -> float:
    """Return milliseconds elapsed since a monotonic nanosecond timestamp."""
    return (time.perf_counter_ns() - start_ns) / 1_000_000


class PerformanceSample(BaseModel):  # pylint: disable=too-many-instance-attributes
    """One application or network performance observation."""

    observed_at_ms: int = Field(default_factory=lambda: time.time_ns() // 1_000_000)
    instance_id: str = Field(default_factory=default_instance_id)
    client_id: str = Field(default_factory=default_client_id)
    sample_type: str
    operation: str
    target_host: str
    target_port: int | None = None
    resolved_ip: str | None = None
    ae200_device_id: str | None = None
    dns_ms: float | None = None
    icmp_min_ms: float | None = None
    icmp_median_ms: float | None = None
    icmp_max_ms: float | None = None
    packet_loss_pct: float | None = None
    lock_wait_ms: float | None = None
    connect_ms: float | None = None
    response_ms: float | None = None
    close_ms: float | None = None
    total_ms: float = 0
    success: bool = False
    outcome: str = "pending"
    error_type: str | None = None
    error_message: str | None = None
    response_bytes: int | None = None
    experiment_id: str | None = Field(default_factory=_default_experiment_id)

    def mark_error(self, error: BaseException) -> None:
        """Attach a normalized error without changing the original exception."""
        self.success = False
        self.outcome = "error"
        self.error_type = type(error).__name__
        self.error_message = str(error)[:MAX_ERROR_MESSAGE_LENGTH]


class PingSummary(BaseModel):
    """Parsed aggregate values from the system ping command."""

    minimum_ms: float | None = None
    median_ms: float | None = None
    maximum_ms: float | None = None
    packet_loss_pct: float
    replies: int


class PerformanceQuery(BaseModel):
    """Validated filters for the performance sample API."""

    start_ms: int
    end_ms: int
    instance_id: str | None = None
    client_id: str | None = None
    sample_type: str | None = None
    operation: str | None = None
    limit: int = Field(default=DEFAULT_QUERY_LIMIT, ge=1, le=MAX_QUERY_LIMIT)


class PerformanceSamplePage(BaseModel):
    """Bounded performance query response with truncation state."""

    samples: list[PerformanceSample]
    truncated: bool


def configured_database_path() -> str | None:
    """Return the test or runtime SQLite path, if configured."""
    return os.getenv(TEST_DB_NAME) or os.getenv(DB_PATH)


def new_ae200_sample(
    operation: str, target_host: str, ae200_device_id: object | None = None
) -> PerformanceSample:
    """Build a request sample with common AE-200 fields."""
    return PerformanceSample(
        sample_type=SAMPLE_TYPE_AE200,
        operation=operation,
        target_host=target_host,
        target_port=AE200_WEBSOCKET_PORT,
        ae200_device_id=(
            None if ae200_device_id is None else str(ae200_device_id)
        ),
    )


def insert_sample(conn: sqlite3.Connection, sample: PerformanceSample) -> int:
    """Insert one sample with the caller's SQLite connection."""
    fields = sample.model_dump()
    columns = tuple(fields)
    placeholders = ", ".join("?" for _column in columns)
    cursor = conn.execute(
        f"INSERT INTO {PERFORMANCE_TABLE} ({', '.join(columns)}) "
        f"VALUES ({placeholders})",
        tuple(fields[column] for column in columns),
    )
    if cursor.lastrowid is None:
        raise sqlite3.DatabaseError("performance sample insert returned no row id")
    return cursor.lastrowid


def record_sample(
    sample: PerformanceSample,
    db_path: str | None = None,
    *,
    timeout_seconds: float = 2,
) -> int:
    """Persist one sample in a short independent transaction."""
    path = db_path or configured_database_path()
    if not path:
        raise RuntimeError(f"{DB_PATH} is not configured")
    with sqlite3.connect(path, timeout=timeout_seconds) as conn:
        sample_id = insert_sample(conn, sample)
        conn.commit()
        return sample_id


def record_sample_best_effort(sample: PerformanceSample) -> None:
    """Record instrumentation without affecting the instrumented operation."""
    try:
        record_sample(
            sample, timeout_seconds=BEST_EFFORT_SQLITE_TIMEOUT_SECONDS
        )
    except (OSError, RuntimeError, sqlite3.Error) as error:
        logger.warning(
            "Could not record %s performance sample: %s",
            sample.sample_type,
            error,
        )


def fetch_sample_page(
    conn: sqlite3.Connection, query: PerformanceQuery
) -> PerformanceSamplePage:
    """Return ordered samples and whether the bounded query was truncated."""
    clauses = ["observed_at_ms >= ?", "observed_at_ms <= ?"]
    values: list[object] = [query.start_ms, query.end_ms]
    for column in ("instance_id", "client_id", "sample_type", "operation"):
        value = getattr(query, column)
        if value is not None:
            clauses.append(f"{column} = ?")
            values.append(value)
    values.append(query.limit + 1)
    rows = conn.execute(
        f"SELECT * FROM {PERFORMANCE_TABLE} "
        f"WHERE {' AND '.join(clauses)} "
        "ORDER BY observed_at_ms, sample_id LIMIT ?",
        values,
    ).fetchall()
    samples = [
        PerformanceSample.model_validate(
            {key: row[key] for key in row.keys() if key != "sample_id"}
        )
        for row in rows[: query.limit]
    ]
    return PerformanceSamplePage(samples=samples, truncated=len(rows) > query.limit)


def fetch_samples(
    conn: sqlite3.Connection, query: PerformanceQuery
) -> list[PerformanceSample]:
    """Return the sample rows from a bounded query."""
    return fetch_sample_page(conn, query).samples


def delete_expired_samples(
    conn: sqlite3.Connection,
    *,
    now_ms: int | None = None,
    retention_days: int | None = None,
) -> int:
    """Delete raw samples older than the configured retention period."""
    days = retention_days
    if days is None:
        days = int(
            os.getenv(
                PERFORMANCE_RETENTION_DAYS_ENV, str(DEFAULT_RETENTION_DAYS)
            )
        )
    if days < 1:
        raise ValueError("performance retention must be at least one day")
    current_ms = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    cutoff_ms = current_ms - days * 24 * 60 * 60 * 1000
    cursor = conn.execute(
        f"DELETE FROM {PERFORMANCE_TABLE} WHERE observed_at_ms < ?", (cutoff_ms,)
    )
    return cursor.rowcount


def parse_ping_output(output: str) -> PingSummary:
    """Parse Linux or macOS ping output without relying on summary wording."""
    values = [float(value) for value in PING_TIME_RE.findall(output)]
    loss_match = PACKET_LOSS_RE.search(output)
    if loss_match is None:
        raise ValueError("ping output did not include packet loss")
    return PingSummary(
        minimum_ms=min(values) if values else None,
        median_ms=statistics.median(values) if values else None,
        maximum_ms=max(values) if values else None,
        packet_loss_pct=float(loss_match.group(1)),
        replies=len(values),
    )


def preferred_stream_address(addresses: list[tuple]) -> str:
    """Prefer IPv4 so the resolved literal works with macOS `ping`."""
    if not addresses:
        raise OSError("DNS returned no addresses")
    for address in addresses:
        if address[0] == socket.AF_INET:
            return str(address[4][0])
    return str(addresses[0][4][0])


def resolve_target(host: str) -> tuple[str, float]:
    """Resolve a target, preferring IPv4, and return its lookup time."""
    started_ns = time.perf_counter_ns()
    addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    dns_ms = elapsed_ms(started_ns)
    if not addresses:
        raise OSError(f"DNS returned no addresses for {host}")
    return preferred_stream_address(addresses), dns_ms


def run_ping(host: str, count: int = 3, timeout_seconds: float = 10) -> tuple[PingSummary, float]:
    """Run the platform ping command and return its parsed output and duration."""
    started_ns = time.perf_counter_ns()
    completed = subprocess.run(
        ["ping", "-n", "-c", str(count), host],
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout_seconds,
    )
    total_ms = elapsed_ms(started_ns)
    output = "\n".join((completed.stdout, completed.stderr))
    summary = parse_ping_output(output)
    return summary, total_ms


def probe_tcp_reject(
    host: str,
    port: int,
    *,
    resolved_ip: str | None = None,
    timeout_seconds: float = 3,
) -> PerformanceSample:
    """Measure a TCP connection attempt to a port expected to reject it."""
    sample = PerformanceSample(
        sample_type=SAMPLE_TYPE_TCP_REJECT,
        operation=OPERATION_REJECT,
        target_host=host,
        target_port=port,
        resolved_ip=resolved_ip,
    )
    started_ns = time.perf_counter_ns()
    try:
        with socket.create_connection(
            (resolved_ip or host, port), timeout=timeout_seconds
        ):
            sample.connect_ms = elapsed_ms(started_ns)
            sample.success = True
            sample.outcome = "connected"
    except ConnectionRefusedError:
        sample.connect_ms = elapsed_ms(started_ns)
        sample.success = True
        sample.outcome = "refused"
    except OSError as error:
        sample.connect_ms = elapsed_ms(started_ns)
        sample.mark_error(error)
    sample.total_ms = elapsed_ms(started_ns)
    return sample


def collect_network_samples(
    host: str,
    *,
    reject_port: int = DEFAULT_REJECT_PORT,
    ping_count: int = 3,
) -> list[PerformanceSample]:
    """Collect DNS, ICMP, and TCP-reject samples for one target."""
    samples: list[PerformanceSample] = []
    resolved_ip: str | None = None
    dns_sample = PerformanceSample(
        sample_type=SAMPLE_TYPE_DNS,
        operation=OPERATION_RESOLVE,
        target_host=host,
    )
    dns_started_ns = time.perf_counter_ns()
    try:
        resolved_ip, dns_sample.dns_ms = resolve_target(host)
        dns_sample.resolved_ip = resolved_ip
        dns_sample.success = True
        dns_sample.outcome = "resolved"
    except OSError as error:
        dns_sample.mark_error(error)
    dns_sample.total_ms = elapsed_ms(dns_started_ns)
    samples.append(dns_sample)

    ping_sample = PerformanceSample(
        sample_type=SAMPLE_TYPE_ICMP,
        operation=OPERATION_ECHO,
        target_host=host,
        resolved_ip=resolved_ip,
    )
    ping_started_ns = time.perf_counter_ns()
    try:
        ping, ping_sample.total_ms = run_ping(
            resolved_ip or host, count=ping_count
        )
        ping_sample.icmp_min_ms = ping.minimum_ms
        ping_sample.icmp_median_ms = ping.median_ms
        ping_sample.icmp_max_ms = ping.maximum_ms
        ping_sample.packet_loss_pct = ping.packet_loss_pct
        ping_sample.success = ping.replies > 0
        ping_sample.outcome = "reply" if ping.replies > 0 else "no_reply"
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        ping_sample.total_ms = elapsed_ms(ping_started_ns)
        ping_sample.mark_error(error)
    samples.append(ping_sample)

    samples.append(
        probe_tcp_reject(host, reject_port, resolved_ip=resolved_ip)
        if resolved_ip is not None
        else PerformanceSample(
            sample_type=SAMPLE_TYPE_TCP_REJECT,
            operation=OPERATION_REJECT,
            target_host=host,
            target_port=reject_port,
            total_ms=0,
            success=False,
            outcome="dns_failed",
            error_type="DNSFailure",
            error_message="TCP probe skipped because DNS resolution failed",
        )
    )
    return samples
