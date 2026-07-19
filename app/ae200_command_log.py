"""Durable, best-effort audit records for AE-200 write commands."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time

from pydantic import BaseModel, Field

from .constants import DB_PATH, TEST_DB_NAME
from . import performance_monitoring

logger = logging.getLogger(__name__)
TABLE = "ae200_command_log"
DEFAULT_LIMIT = 50
MAX_LIMIT = 500
MAX_ERROR_LENGTH = 500


class AE200SetResponse(BaseModel):
    """High-level acknowledgement returned for one AE-200 setRequest."""

    command: str
    response_fields: dict[str, str]

    def summary(self) -> str:
        values = " ".join(
            f"{key}={value}" for key, value in sorted(self.response_fields.items())
        )
        return f"{self.command}{': ' + values if values else ''}"


class AE200CommandRecord(BaseModel):
    """One completed AE-200 command and its controller-level result."""

    command_id: int | None = None
    requested_at_ms: int
    completed_at_ms: int
    instance_id: str = Field(default_factory=performance_monitoring.default_instance_id)
    client_id: str = Field(default_factory=performance_monitoring.default_client_id)
    ae200_device_id: str
    request: dict[str, str]
    outcome: str
    response_summary: str
    response: dict[str, str] | None = None
    error_type: str | None = None
    error_message: str | None = None


class AE200CommandPage(BaseModel):
    """Most recent command records, newest first."""

    commands: list[AE200CommandRecord]


def new_record(device_id: object, attributes: dict[str, str]) -> AE200CommandRecord:
    """Create a pending record for a command about to be sent."""
    now = time.time_ns() // 1_000_000
    return AE200CommandRecord(
        requested_at_ms=now,
        completed_at_ms=now,
        ae200_device_id=str(device_id),
        request=attributes,
        outcome="error",
        response_summary="pending",
    )


def mark_response(
    record: AE200CommandRecord, response: AE200SetResponse, *, simulated: bool
) -> None:
    """Complete a record with a parsed controller or simulator response."""
    record.completed_at_ms = time.time_ns() // 1_000_000
    record.outcome = "simulated" if simulated else "confirmed"
    record.response_summary = response.summary()
    record.response = response.response_fields


def mark_error(record: AE200CommandRecord, error: BaseException) -> None:
    """Complete a record with a bounded error description."""
    record.completed_at_ms = time.time_ns() // 1_000_000
    record.outcome = "error"
    record.response_summary = f"{type(error).__name__}: {error}"[:MAX_ERROR_LENGTH]
    record.error_type = type(error).__name__
    record.error_message = str(error)[:MAX_ERROR_LENGTH]


def _database_path() -> str | None:
    return os.getenv(TEST_DB_NAME) or os.getenv(DB_PATH)


def insert_record(conn: sqlite3.Connection, record: AE200CommandRecord) -> int:
    """Insert one audit record with the caller's connection."""
    cursor = conn.execute(
        f"""
        INSERT INTO {TABLE} (
            requested_at_ms, completed_at_ms, instance_id, client_id,
            ae200_device_id, request_json, outcome, response_summary,
            response_json, error_type, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.requested_at_ms,
            record.completed_at_ms,
            record.instance_id,
            record.client_id,
            record.ae200_device_id,
            json.dumps(record.request, sort_keys=True, separators=(",", ":")),
            record.outcome,
            record.response_summary,
            (
                json.dumps(record.response, sort_keys=True, separators=(",", ":"))
                if record.response is not None
                else None
            ),
            record.error_type,
            record.error_message,
        ),
    )
    if cursor.lastrowid is None:
        raise sqlite3.DatabaseError("AE-200 command insert returned no row id")
    return cursor.lastrowid


def record_best_effort(record: AE200CommandRecord) -> None:
    """Persist audit data without ever altering the control operation's result."""
    path = _database_path()
    if not path:
        logger.warning("Could not record AE-200 command: %s is not configured", DB_PATH)
        return
    try:
        with sqlite3.connect(path, timeout=0) as conn:
            insert_record(conn, record)
            conn.commit()
    except (OSError, sqlite3.Error) as error:
        logger.warning("Could not record AE-200 command: %s", error)


def fetch_recent(conn: sqlite3.Connection, limit: int = DEFAULT_LIMIT) -> AE200CommandPage:
    """Return at most ``limit`` command audit rows, newest first."""
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    rows = conn.execute(
        f"SELECT * FROM {TABLE} ORDER BY requested_at_ms DESC, command_id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return AE200CommandPage(
        commands=[
            AE200CommandRecord(
                command_id=row["command_id"],
                requested_at_ms=row["requested_at_ms"],
                completed_at_ms=row["completed_at_ms"],
                instance_id=row["instance_id"],
                client_id=row["client_id"],
                ae200_device_id=row["ae200_device_id"],
                request=json.loads(row["request_json"]),
                outcome=row["outcome"],
                response_summary=row["response_summary"],
                response=(json.loads(row["response_json"]) if row["response_json"] else None),
                error_type=row["error_type"],
                error_message=row["error_message"],
            )
            for row in rows
        ]
    )
