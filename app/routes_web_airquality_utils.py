"""Helpers for air-quality specific web rendering and scoring."""

import datetime
import time
from typing import Any, Optional

from .aq_metrics import VALUE_KEY
from .models import (
    AirMetricRange,
    AirMetricRule,
    AirMetricScore,
    AirMetricThreshold,
    AirQualityAnnotation,
)
from .util import github_style_duration


# Data-driven thresholds to keep branching complexity low.
# Each entry maps a metric name to a short display name and ordered thresholds:
# thresholds are evaluated from highest to lowest.
_METRIC_RULES: dict[str, AirMetricRule] = {
    "co2": AirMetricRule(
        short_name="CO₂",
        thresholds=[
            AirMetricThreshold(limit=1200, score=2, label="problem"),
            AirMetricThreshold(limit=800, score=1, label="elevated"),
        ],
    ),
    "pm25": AirMetricRule(
        short_name="PM2.5",
        thresholds=[
            AirMetricThreshold(limit=35, score=2, label="problem"),
            AirMetricThreshold(limit=12, score=1, label="elevated"),
        ],
    ),
    "pm1": AirMetricRule(
        short_name="PM1",
        thresholds=[
            AirMetricThreshold(limit=35, score=2, label="problem"),
            AirMetricThreshold(limit=12, score=1, label="elevated"),
        ],
    ),
    "humidity": AirMetricRule(
        short_name="RH",
        ranges=AirMetricRange(
            problem_min=30,
            problem_max=60,
            elevated_min=35,
            elevated_max=55,
        ),
    ),
    "temp": AirMetricRule(
        short_name="Temp",
        ranges=AirMetricRange(
            problem_min=18,
            problem_max=27,
            elevated_min=20,
            elevated_max=25,
        ),
    ),
    "radonShortTermAvg": AirMetricRule(
        short_name="Radon",
        thresholds=[
            AirMetricThreshold(limit=150, score=2, label="problem"),
            AirMetricThreshold(limit=100, score=1, label="elevated"),
        ],
    ),
    "voc": AirMetricRule(
        short_name="VOC",
        thresholds=[
            AirMetricThreshold(limit=2000, score=2, label="problem"),
            AirMetricThreshold(limit=500, score=1, label="elevated"),
        ],
    ),
}


def _score_with_thresholds(
    value: float, thresholds: list[AirMetricThreshold]
) -> AirMetricScore:
    for threshold in thresholds:
        if value > threshold.limit:
            return AirMetricScore(
                severity_score=threshold.score,
                label=threshold.label,
                short_name="",
            )
    return AirMetricScore(severity_score=0, label="good", short_name="")


def _score_with_ranges(value: float, ranges: AirMetricRange) -> AirMetricScore:
    if value < ranges.problem_min or value > ranges.problem_max:
        return AirMetricScore(severity_score=2, label="problem", short_name="")
    if value < ranges.elevated_min or value > ranges.elevated_max:
        return AirMetricScore(severity_score=1, label="elevated", short_name="")
    return AirMetricScore(severity_score=0, label="good", short_name="")


def score_air_metric_model(metric_name: str, value: Any) -> AirMetricScore:
    """Return a structured severity score for a metric value.

    severity_score: 0=good, 1=elevated, 2=problem
    """
    if value is None:
        return AirMetricScore(severity_score=0, label="good", short_name=metric_name)

    rules = _METRIC_RULES.get(metric_name)
    if not rules:
        return AirMetricScore(severity_score=0, label="good", short_name=metric_name)

    numeric_value = float(value)

    if rules.thresholds:
        score = _score_with_thresholds(numeric_value, rules.thresholds)
    elif rules.ranges is not None:
        score = _score_with_ranges(numeric_value, rules.ranges)
    else:
        score = AirMetricScore(severity_score=0, label="good", short_name="")

    return AirMetricScore(
        severity_score=score.severity_score,
        label=score.label,
        short_name=rules.short_name,
    )


def score_air_metric(metric_name: str, value: Any) -> tuple[int, str, str]:
    """Return (severity_score, label, short_name) for a metric value."""
    return score_air_metric_model(metric_name, value).as_tuple()


def _air_quality_annotation(status: dict[str, Any]) -> AirQualityAnnotation:
    """Build template CSS annotations for one indoor air-quality status payload."""
    cell_classes: dict[str, str] = {}
    for metric_name in [
        "co2",
        "pm25",
        "pm1",
        "humidity",
        "temp",
        "radonShortTermAvg",
        "voc",
    ]:
        val_dict = status.get(metric_name)
        value: Optional[float]
        if isinstance(val_dict, dict):
            value = val_dict.get(VALUE_KEY)
        elif isinstance(val_dict, (int, float)):
            value = float(val_dict)
        else:
            value = None

        score = score_air_metric_model(metric_name, value)
        if score.severity_score == 1:
            cell_classes[metric_name] = "aq-elevated"
        elif score.severity_score == 2:
            cell_classes[metric_name] = "aq-problem"
    return AirQualityAnnotation(aq_classes=cell_classes)


def annotate_air_quality_cells(airmon: list[dict[str, Any]]) -> None:
    """Annotate indoor air-quality rows with CSS classes based on metric severity."""
    for row in airmon:
        status = row.get("status") or {}
        if "aqi" in status:
            continue

        annotation = _air_quality_annotation(status)
        if annotation.aq_classes:
            row["aq_classes"] = annotation.aq_classes


def annotate_staleness(airmon: list[dict[str, Any]]) -> None:
    """Add ``age`` and ``is_stale`` to each device row for template rendering."""
    now_ts = int(time.time())
    for row in airmon:
        if "logtime" in row:
            last_update = row["logtime"] + row.get("duration", 1)
            row["age"] = github_style_duration(last_update)
            row["is_stale"] = (now_ts - last_update) >= 300
        else:
            row["age"] = None
            row["is_stale"] = False


def format_unix_as_asc(ts: Optional[int]) -> Optional[str]:
    """Format a Unix timestamp (seconds) as a human-readable string."""
    if ts is None:
        return None
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
