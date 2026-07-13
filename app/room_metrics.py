"""Typed room membership, freshness, and metric source selection."""

from enum import StrEnum
import math
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict

from .aq_metrics import extract_metric_from_status
from .constants import TEMP_SOURCE_STALE_SECONDS
from .device_types import DEVICE_TYPE_ERV, DEVICE_TYPE_INTERNAL
from .models import StatusPayload


class RoomMetric(StrEnum):
    """Metrics selected through the shared room source path."""

    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"


class RoomMetricExclusionReason(StrEnum):
    """Why a latest device reading was not selected."""

    DEVICE_TYPE = "device_type"
    ROOM = "room"
    STALE = "stale"
    MISSING_METRIC = "missing_metric"


class RoomMetricSnapshot(BaseModel):
    """Latest raw database reading and persisted device metadata."""

    model_config = ConfigDict(frozen=True)

    device_id: int
    device_name: str
    display_name: str | None = None
    device_type: str | None = None
    room_id: int | None = None
    logtime: float
    duration: float = 0
    temp10x: int | None = None
    status: StatusPayload | None = None


class RoomMetricSource(BaseModel):
    """One current, eligible metric reading selected for a room."""

    model_config = ConfigDict(frozen=True)

    device_id: int
    device_name: str
    display_name: str | None = None
    device_type: str | None = None
    room_id: int | None = None
    metric: RoomMetric
    value: float
    unit: Literal["celsius", "percent"]
    logtime: float
    duration: float
    age_seconds: int


class RoomMetricExclusion(BaseModel):
    """One device omitted from a room metric selection."""

    model_config = ConfigDict(frozen=True)

    device_id: int
    reason: RoomMetricExclusionReason


class RoomMetricSelection(BaseModel):
    """Selected room readings plus explicit exclusion outcomes."""

    model_config = ConfigDict(frozen=True)

    room_id: int | None
    metric: RoomMetric
    at_time: float
    stale_seconds: int
    sources: list[RoomMetricSource]
    exclusions: list[RoomMetricExclusion]


def reading_age_seconds(snapshot: RoomMetricSnapshot, at_time: float) -> int:
    """Return whole seconds since the reading's validity interval ended."""
    return int(max(0, at_time - (snapshot.logtime + snapshot.duration)))


def _metric_value(
    snapshot: RoomMetricSnapshot,
    metric: RoomMetric,
) -> tuple[float | None, Literal["celsius", "percent"]]:
    if metric == RoomMetric.TEMPERATURE:
        value = snapshot.temp10x / 10 if snapshot.temp10x is not None else None
        return value, "celsius"
    value = (
        extract_metric_from_status(snapshot.status, "humidity")
        if snapshot.status is not None
        else None
    )
    return value, "percent"


def select_room_metric_sources(
    snapshots: Iterable[RoomMetricSnapshot],
    *,
    room_id: int | None,
    metric: RoomMetric,
    at_time: float,
    stale_seconds: int = TEMP_SOURCE_STALE_SECONDS,
) -> RoomMetricSelection:
    """Select current physical-device readings belonging to one room."""
    sources = []
    exclusions = []
    excluded_types = {DEVICE_TYPE_ERV, DEVICE_TYPE_INTERNAL}
    for snapshot in snapshots:
        device_type = (snapshot.device_type or "").upper()
        reason = None
        age_seconds = reading_age_seconds(snapshot, at_time)
        if device_type in excluded_types:
            reason = RoomMetricExclusionReason.DEVICE_TYPE
        elif snapshot.room_id != room_id:
            reason = RoomMetricExclusionReason.ROOM
        elif age_seconds > stale_seconds:
            reason = RoomMetricExclusionReason.STALE
        else:
            value, unit = _metric_value(snapshot, metric)
            if value is None or not math.isfinite(value):
                reason = RoomMetricExclusionReason.MISSING_METRIC
            else:
                sources.append(
                    RoomMetricSource(
                        device_id=snapshot.device_id,
                        device_name=snapshot.device_name,
                        display_name=snapshot.display_name,
                        device_type=snapshot.device_type,
                        room_id=snapshot.room_id,
                        metric=metric,
                        value=value,
                        unit=unit,
                        logtime=snapshot.logtime,
                        duration=snapshot.duration,
                        age_seconds=age_seconds,
                    )
                )
        if reason is not None:
            exclusions.append(
                RoomMetricExclusion(device_id=snapshot.device_id, reason=reason)
            )
    return RoomMetricSelection(
        room_id=room_id,
        metric=metric,
        at_time=at_time,
        stale_seconds=stale_seconds,
        sources=sources,
        exclusions=exclusions,
    )
