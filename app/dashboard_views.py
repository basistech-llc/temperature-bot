"""View models and builders for the main dashboard page.

The dashboard used to hand Jinja a ``list[dict[str, Any]]`` that route code had
progressively mutated with display-only keys. A misspelled or forgotten key was
invisible: Jinja renders an unknown attribute as the empty string rather than
failing, so the page simply lost a label. These models make the contract
between the route and ``index.html`` explicit and checkable.

Two rules make that work:

- ``DashboardDeviceView`` sets ``extra="forbid"``. A key the database layer
  starts emitting, or a display field this module forgets to declare, raises at
  build time instead of quietly vanishing from the page.
- Every field ``index.html`` reads is declared here. Fields the template shows
  unconditionally are required, so omitting one is an error rather than a blank
  cell.

Why the flags may default to ``False`` rather than staying absent: Jinja treats
an undefined attribute and ``False`` identically — ``Undefined`` is falsy and
interpolates to ``''`` — and ``index.html`` guards every one of them with
``{% if %}`` or ``|default(x, true)``. That equivalence does *not* hold for
JSON, where absent and ``false`` are different to a client, which is why
``/api/v1/status`` and ``/api/v1/devices`` still serve raw dictionaries and are
tracked separately in GitHub #182's sibling issue.

These models live here rather than in ``models.py`` because they are
presentation contracts owned by one page, not data crossing module boundaries.
``models.py`` remains the home for everything shared.
"""

import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .device_types import (
    DEVICE_TYPE_ERV,
    DEVICE_TYPE_FCU,
    DEVICE_TYPE_INTERNAL,
    DEVICE_TYPE_SENSOR,
)
from .constants import DASHBOARD_AIR_QUALITY_DEVICE_EXPIRATION_SECONDS
from .display_names import append_display_icon, display_device_name
from .models import DeviceStatus, Room
from .routes_web_airquality_utils import format_unix_as_asc
from .util import github_style_duration

DASHBOARD_DEVICE_ICONS = {
    DEVICE_TYPE_ERV: "♻️",
    DEVICE_TYPE_FCU: "🌀",
    DEVICE_TYPE_SENSOR: "📡",
}


class DashboardDeviceView(DeviceStatus):
    """One device row as ``index.html`` consumes it.

    Inherits the persisted columns from :class:`~app.models.DeviceStatus` so the
    two cannot drift, and adds the values ``db.get_device_status()`` derives plus
    the labels this module computes.
    """

    model_config = ConfigDict(extra="forbid")

    # Derived by db.get_device_status() from devlog.status_json. Present only
    # for rows that actually have a status, hence the defaults.
    #
    # drive and fan_speed are AE-200 integer codes, not names, despite the
    # lookup tables being called DRIVE_NAMES/FAN_SPEED_NAMES: those map
    # name -> code (`{value: key for key, value in DRIVES.items()}`), so
    # extract_drive_and_fan_speed turns the status_json string "ON" into 1.
    # index.html does not read either field; they are declared because
    # extra="forbid" requires every key present on the row.
    drive: int | None = None
    fan_speed: int | None = None
    has_speed_control: bool = False

    # One flag per AQ_METRIC_STATUS_KEYS entry. Kept flat (has_co2, not
    # metrics.co2) so index.html needs no edits; test_dashboard_views.py asserts
    # this set stays in step with AQ_METRIC_STATUS_KEYS.
    has_co2: bool = False
    has_humidity: bool = False
    has_pm1: bool = False
    has_pm25: bool = False
    has_pressure: bool = False
    has_radon: bool = False
    has_voc: bool = False

    # Computed by this module. Required: the template renders each of these
    # unconditionally, so a missing one is a bug, not an empty cell.
    device_label: str
    device_label_with_icon: str
    device_update_text: str
    device_update_tooltip: str
    dashboard_air_quality_active: bool = False


class RoomMatrixGroup(BaseModel):
    """One room section in the main-page sensor matrix."""

    room_id: int | None = None
    room_name: str
    fcu_device_id: int | None = None
    calculated_temp10x: int | None = None
    calculated_humidity: float | None = None
    can_delete: bool = False
    devices: list[DashboardDeviceView] = Field(default_factory=list)


class TableUpdateSummary(BaseModel):
    """Oldest timestamp represented by the data currently shown in a table."""

    oldest_update_at: int
    oldest_update_datetime: str
    oldest_update_age: str
    source_device_name: str | None = None
    label: str


class DashboardPage(BaseModel):
    """Everything ``index.html`` renders, assembled before the template runs."""

    model_config = ConfigDict(extra="forbid")

    devices: list[DashboardDeviceView] = Field(default_factory=list)
    room_groups: list[RoomMatrixGroup] = Field(default_factory=list)
    table_update_summaries: dict[str, TableUpdateSummary | None] = Field(
        default_factory=dict
    )
    now: int


def status_update_timestamp(row: dict[str, Any]) -> int | None:
    """Return the timestamp when a status row stopped being current."""
    try:
        logtime = int(row["logtime"])
    except (KeyError, TypeError, ValueError):
        return None

    try:
        duration_value = row.get("duration", 1)
        duration = int(1 if duration_value is None else duration_value)
    except (TypeError, ValueError):
        duration = 1
    return logtime + duration


def air_quality_device_is_active(device: dict[str, Any], now: int) -> bool:
    """Return whether a device belongs in the dashboard Air Quality table."""
    if device.get("has_speed_control") or device.get("temp10x") is None:
        return False
    updated_at = status_update_timestamp(device)
    if updated_at is None:
        return False
    return now - updated_at <= DASHBOARD_AIR_QUALITY_DEVICE_EXPIRATION_SECONDS


def device_label(device: dict[str, Any]) -> str:
    """Return a dashboard label without doing live network enrichment."""
    raw_name = device.get("device_name", "")
    status = device.get("status") or {}
    stored_label = status.get("label") if isinstance(status, dict) else None
    return device.get("display_name") or display_device_name(
        raw_name,
        hubitat_label=stored_label,
        source="db",
    )


def device_label_with_icon(device: dict[str, Any]) -> str:
    """Return the server-rendered label with one device-category marker."""
    label = str(device.get("device_label") or device_label(device))
    device_type = str(device.get("device_type") or "").upper()
    icon = DASHBOARD_DEVICE_ICONS.get(device_type, "")
    if not icon and device.get("dashboard_air_quality_active"):
        icon = DASHBOARD_DEVICE_ICONS[DEVICE_TYPE_SENSOR]
    return append_display_icon(label, icon)


def device_update_text(device: dict[str, Any], now: int) -> str:
    """Return the last-update text shown in device metadata UI."""
    updated_at = status_update_timestamp(device)
    if updated_at is None:
        return ""
    updated_datetime = format_unix_as_asc(updated_at) or ""
    updated_age = github_style_duration(updated_at, now=now)
    return f"{updated_datetime} - {updated_age} ago"


def device_update_tooltip(device: dict[str, Any], now: int) -> str:
    """Return the Unit-column tooltip for a device row."""
    raw_device_name = device.get("device_name", "")
    name = raw_device_name if isinstance(raw_device_name, str) else ""
    update_text = device_update_text(device, now)
    if not update_text:
        return name
    return f"{name}\nLast updated at {update_text}"


def annotate_device_rows(rows: list[dict[str, Any]], now: int) -> None:
    """Add the display-only keys to raw status rows, in place.

    Kept separate from validation so the annotate-then-validate sequence stays
    visible: ``extra="forbid"`` only catches a forgotten key if the key is added
    before the model is built.
    """
    for row in rows:
        row["device_label"] = device_label(row)
        row["dashboard_air_quality_active"] = air_quality_device_is_active(row, now)
        row["device_label_with_icon"] = device_label_with_icon(row)
        row["device_update_text"] = device_update_text(row, now)
        row["device_update_tooltip"] = device_update_tooltip(row, now)


def table_update_summary(
    devices: list[dict[str, Any]],
    include_device: Callable[[dict[str, Any]], bool],
    now: int,
) -> TableUpdateSummary | None:
    """Summarize the oldest updated timestamp represented in a table."""
    candidates = [
        (update_time, device_label(device))
        for device in devices
        if include_device(device)
        for update_time in [status_update_timestamp(device)]
        if update_time is not None
    ]
    if not candidates:
        return None

    oldest_update_at, source_device_name = min(candidates, key=lambda item: item[0])
    oldest_update_datetime = format_unix_as_asc(oldest_update_at) or ""
    oldest_update_age = github_style_duration(oldest_update_at, now=now)
    return TableUpdateSummary(
        oldest_update_at=oldest_update_at,
        oldest_update_datetime=oldest_update_datetime,
        oldest_update_age=oldest_update_age,
        source_device_name=source_device_name,
        label=(
            f"(oldest update at {oldest_update_datetime} - "
            f"{oldest_update_age} ago from {source_device_name})"
        ),
    )


def index_table_update_summaries(
    devices: list[dict[str, Any]], now: int
) -> dict[str, TableUpdateSummary | None]:
    """Build update summaries for the index page's three device tables."""
    return {
        "erv": table_update_summary(
            devices,
            lambda device: device.get("device_type") == "ERV",
            now,
        ),
        "fcu": table_update_summary(
            devices,
            lambda device: device.get("device_type") == "FCU",
            now,
        ),
        "air_quality": table_update_summary(
            devices,
            lambda device: air_quality_device_is_active(device, now),
            now,
        ),
    }


def room_matrix_groups(
    devices: list[dict[str, Any]],
    rooms: list[Room],
    assigned_room_ids: set[int],
) -> list[RoomMatrixGroup]:
    """Group active sensor rows by canonical room, including empty rooms."""
    fcu_by_room = {
        device.get("room_id"): device
        for device in devices
        if str(device.get("device_type") or "").upper() == DEVICE_TYPE_FCU
        and device.get("room_id") is not None
    }
    groups = {
        room.room_id: RoomMatrixGroup(
            room_id=room.room_id,
            room_name=room.room_name or "Unnamed room",
            fcu_device_id=(fcu_by_room.get(room.room_id) or {}).get("device_id"),
            calculated_temp10x=(fcu_by_room.get(room.room_id) or {}).get(
                "calculated_temp10x"
            ),
            calculated_humidity=(fcu_by_room.get(room.room_id) or {}).get(
                "calculated_humidity"
            ),
            can_delete=(
                room.fcu_device_id is None and room.room_id not in assigned_room_ids
            ),
        )
        for room in rooms
    }
    groups[None] = RoomMatrixGroup(room_name="Unassigned")
    for device in devices:
        if not device.get("dashboard_air_quality_active") or device.get(
            "device_type"
        ) in {DEVICE_TYPE_ERV, DEVICE_TYPE_FCU, DEVICE_TYPE_INTERNAL}:
            continue
        room_id = device.get("room_id")
        groups.setdefault(
            room_id,
            RoomMatrixGroup(
                room_id=room_id,
                room_name=device.get("room_name") or "Unassigned",
            ),
        ).devices.append(DashboardDeviceView.model_validate(device))
    for group in groups.values():
        group.devices.sort(
            key=lambda device: (
                (device.display_name or device.device_name).casefold(),
                device.device_id,
            )
        )
    return sorted(groups.values(), key=lambda group: group.room_name.casefold())


def build_dashboard_page(
    rows: list[dict[str, Any]],
    rooms: list[Room],
    assigned_room_ids: set[int],
    now: int | None = None,
) -> DashboardPage:
    """Assemble the whole dashboard contract from raw status rows.

    ``rows`` are annotated in place first, then validated. Building the models
    from the annotated dictionaries (rather than assigning fields one by one) is
    what makes ``extra="forbid"`` useful: a key nobody declared raises here,
    where it is a visible failure, instead of disappearing into the template.
    """
    now = int(time.time()) if now is None else now
    annotate_device_rows(rows, now)
    return DashboardPage(
        devices=[DashboardDeviceView.model_validate(row) for row in rows],
        room_groups=room_matrix_groups(rows, rooms, assigned_room_ids),
        table_update_summaries=index_table_update_summaries(rows, now),
        now=now,
    )
