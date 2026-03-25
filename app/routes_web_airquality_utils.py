"""Helpers for air-quality specific web rendering and scoring."""

import datetime
import time
from typing import Dict, Any, List, Optional, Tuple

from .util import github_style_duration


# Data-driven thresholds to keep branching complexity low.
# Each entry maps a metric name to a short display name and ordered thresholds:
# thresholds are evaluated from highest to lowest.
_METRIC_RULES: Dict[str, Dict[str, Any]] = {
    "co2": {
        "short_name": "CO₂",
        "thresholds": [(1200, 2, "problem"), (800, 1, "elevated")],
    },
    "pm25": {
        "short_name": "PM2.5",
        "thresholds": [(35, 2, "problem"), (12, 1, "elevated")],
    },
    "pm1": {
        "short_name": "PM1",
        "thresholds": [(35, 2, "problem"), (12, 1, "elevated")],
    },
    "humidity": {
        "short_name": "RH",
        # Problem outside [30, 60], elevated just outside [35, 55].
        "ranges": {
            "problem": lambda v: v < 30 or v > 60,
            "elevated": lambda v: (30 <= v < 35) or (55 < v <= 60),
        },
    },
    "temp": {
        "short_name": "Temp",
        # Problem outside [18, 27], elevated just outside [20, 25].
        "ranges": {
            "problem": lambda v: v < 18 or v > 27,
            "elevated": lambda v: (18 <= v < 20) or (25 < v <= 27),
        },
    },
    "radonShortTermAvg": {
        "short_name": "Radon",
        "thresholds": [(150, 2, "problem"), (100, 1, "elevated")],
    },
    "voc": {
        "short_name": "VOC",
        "thresholds": [(2000, 2, "problem"), (500, 1, "elevated")],
    },
}


def _score_with_thresholds(
    value: float, thresholds: List[Tuple[float, int, str]]
) -> Tuple[int, str]:
    for limit, score, label in thresholds:
        if value > limit:
            return score, label
    return 0, "good"


def _score_with_ranges(
    value: float, ranges: Dict[str, Any]
) -> Tuple[int, str]:
    if ranges["problem"](value):
        return 2, "problem"
    if ranges["elevated"](value):
        return 1, "elevated"
    return 0, "good"


def score_air_metric(metric_name: str, value: Any) -> Tuple[int, str, str]:
    """Return (severity_score, label, short_name) for a metric value.

    severity_score: 0=good, 1=elevated, 2=problem
    """
    if value is None:
        return (0, "good", metric_name)

    rules = _METRIC_RULES.get(metric_name)
    if not rules:
        return (0, "good", metric_name)

    short_name = rules["short_name"]
    numeric_value = float(value)

    if "thresholds" in rules:
        score, label = _score_with_thresholds(numeric_value, rules["thresholds"])
    else:
        score, label = _score_with_ranges(numeric_value, rules["ranges"])

    return (score, label, short_name)


def annotate_air_quality_cells(airmon: List[Dict[str, Any]]) -> None:
    """Annotate indoor air-quality rows with CSS classes based on metric severity."""
    for row in airmon:
        status = row.get("status") or {}
        if "aqi" in status:
            continue

        cell_classes: Dict[str, str] = {}
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
                value = val_dict.get("value")
            elif isinstance(val_dict, (int, float)):
                value = float(val_dict)
            else:
                value = None

            score, _label, _short_name = score_air_metric(metric_name, value)
            if score == 1:
                cell_classes[metric_name] = "aq-elevated"
            elif score == 2:
                cell_classes[metric_name] = "aq-problem"

        if cell_classes:
            row["aq_classes"] = cell_classes


def annotate_staleness(airmon: List[Dict[str, Any]]) -> None:
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
