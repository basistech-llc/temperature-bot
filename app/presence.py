"""Canonical room presence policy."""

import time

from .models import PresenceState, RoomPresence

PRESENCE_STALE_SECONDS = 15 * 60


def get_room_presence(
    conn, *, at_time: int | None = None, stale_after: int = PRESENCE_STALE_SECONDS
) -> list[RoomPresence]:
    """Compute room presence from each assigned device's latest observation."""
    now = int(time.time()) if at_time is None else int(at_time)
    rows = conn.execute(
        """
        WITH latest AS (
            SELECT p.*, ROW_NUMBER() OVER (
                PARTITION BY p.device_id ORDER BY p.observed_at DESC, p.presence_event_id DESC
            ) AS rank
            FROM presence_events p
            JOIN devices d ON d.device_id=p.device_id
            WHERE p.observed_at<=? AND d.room_id=p.room_id
        )
        SELECT r.room_id, r.room_name, l.device_id, l.observed_at, l.present
        FROM rooms r
        LEFT JOIN latest l ON l.room_id=r.room_id AND l.rank=1
        ORDER BY r.room_name COLLATE NOCASE, r.room_id
        """,
        (now,),
    ).fetchall()
    grouped: dict[int, RoomPresence] = {}
    fresh_states: dict[int, list[bool]] = {}
    for row in rows:
        room_id = int(row["room_id"])
        room = grouped.setdefault(
            room_id,
            RoomPresence(
                room_id=room_id,
                room_name=row["room_name"],
                state=PresenceState.UNKNOWN,
            ),
        )
        if row["device_id"] is None:
            continue
        observed_at = int(row["observed_at"])
        room.source_device_ids.append(int(row["device_id"]))
        room.observed_at = max(room.observed_at or observed_at, observed_at)
        if now - observed_at <= stale_after:
            fresh_states.setdefault(room_id, []).append(bool(row["present"]))
        elif room.state == PresenceState.UNKNOWN:
            room.state = PresenceState.STALE
    for room_id, states in fresh_states.items():
        grouped[room_id].state = (
            PresenceState.PRESENT if any(states) else PresenceState.ABSENT
        )
    return list(grouped.values())


def get_presence_for_room(conn, room_id: int, **kwargs) -> RoomPresence:
    """Rules-facing lookup using the same canonical policy as the UI."""
    for room in get_room_presence(conn, **kwargs):
        if room.room_id == room_id:
            return room
    raise LookupError(f"Unknown room_id: {room_id}")
