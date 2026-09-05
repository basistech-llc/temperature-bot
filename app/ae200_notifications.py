"""Parse, persist, and query unsolicited AE-200 state notifications."""

from __future__ import annotations

import json
import sqlite3
import time
import xml.etree.ElementTree as ET

from pydantic import BaseModel, Field

from . import performance_monitoring

TABLE = "ae200_notifications"
DEFAULT_LIMIT = 50
MAX_LIMIT = 500
DEFAULT_RETENTION_DAYS = 90
MILLISECONDS_PER_DAY = 86_400_000
AE200_GROUP_KEY = "Group"
AE200_ADDRESS_KEY = "Address"


class AE200Notification(BaseModel):
    """One Mnet change carried by an unsolicited notifyRequest frame."""

    notification_id: int | None = None
    observed_at_ms: int = Field(default_factory=lambda: time.time_ns() // 1_000_000)
    instance_id: str = Field(default_factory=performance_monitoring.default_instance_id)
    ae200_group_id: str | None = None
    ae200_address: str | None = None
    values: dict[str, str]


class AE200NotificationPage(BaseModel):
    """Newest controller observations, ordered newest first."""

    notifications: list[AE200Notification]


def parse_notification_frame(raw: str) -> list[AE200Notification]:
    """Parse all Mnet changes from one unsolicited XML frame."""
    xml_start = raw.find("<?xml")
    root = ET.fromstring(raw[xml_start:] if xml_start >= 0 else raw)
    command = root.findtext("./Command") or ""
    if command != "notifyRequest":
        raise ValueError(f"expected notifyRequest, received {command or 'no command'}")
    notifications = []
    for node in root.findall("./DatabaseManager/Mnet"):
        values = {str(key): str(value) for key, value in node.attrib.items()}
        group_id = values.pop(AE200_GROUP_KEY, None)
        address = values.pop(AE200_ADDRESS_KEY, None)
        if group_id is None and address is None:
            continue
        notifications.append(
            AE200Notification(
                ae200_group_id=group_id,
                ae200_address=address,
                values=values,
            )
        )
    return notifications


def insert_notifications(
    conn: sqlite3.Connection, notifications: list[AE200Notification]
) -> int:
    """Persist a notification frame atomically and return its event count."""
    conn.executemany(
        f"""
        INSERT INTO {TABLE} (
            observed_at_ms, instance_id, ae200_group_id, ae200_address, values_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                event.observed_at_ms,
                event.instance_id,
                event.ae200_group_id,
                event.ae200_address,
                json.dumps(event.values, sort_keys=True, separators=(",", ":")),
            )
            for event in notifications
        ],
    )
    return len(notifications)


def delete_expired(
    conn: sqlite3.Connection,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    now_ms: int | None = None,
) -> int:
    """Delete observations older than the configured retention window."""
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    current_ms = now_ms if now_ms is not None else time.time_ns() // 1_000_000
    cutoff_ms = current_ms - (
        retention_days * MILLISECONDS_PER_DAY
    )
    cursor = conn.execute(
        f"DELETE FROM {TABLE} WHERE observed_at_ms < ?", (cutoff_ms,)
    )
    return cursor.rowcount


def fetch_recent(
    conn: sqlite3.Connection, limit: int = DEFAULT_LIMIT
) -> AE200NotificationPage:
    """Return at most ``limit`` observations, newest first."""
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    rows = conn.execute(
        f"SELECT * FROM {TABLE} "
        "ORDER BY observed_at_ms DESC, notification_id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return AE200NotificationPage(
        notifications=[
            AE200Notification(
                notification_id=row["notification_id"],
                observed_at_ms=row["observed_at_ms"],
                instance_id=row["instance_id"],
                ae200_group_id=row["ae200_group_id"],
                ae200_address=row["ae200_address"],
                values=json.loads(row["values_json"]),
            )
            for row in rows
        ]
    )
