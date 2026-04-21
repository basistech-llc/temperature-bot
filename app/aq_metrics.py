"""
Indoor air-quality metric plumbing.

The home page and /air-quality page expose click-to-chart behavior for each
reading in ``devlog.status_json`` (CO2, humidity, VOC, radon, PM2.5, PM1,
pressure). This module owns the metric name <-> status_json key mapping and
the value-extraction helpers shared between the status snapshot path
(``db.get_device_status``) and the time-series path
(``db.get_device_metric_series``).

Kept separate from ``db.py`` because ``db.py`` is already at the
too-many-lines ceiling and because these helpers form a small,
self-contained unit that is easier to reason about in isolation.
"""

from typing import Any, Dict


# URL-safe metric name -> top-level key in devlog.status_json.
# Used by the Air Quality click-to-chart feature: main-page cells link to
# /metric_chart?metric=<key>, and /api/v1/metric looks up the status_json key.
AQ_METRIC_STATUS_KEYS: Dict[str, str] = {
    "humidity": "humidity",
    "co2": "co2",
    "voc": "voc",
    "radon": "radonShortTermAvg",
    "pm25": "pm25",
    "pm1": "pm1",
    "pressure": "pressure",
}


def coerce_metric_value(raw: Any) -> float | None:
    """Coerce a status_json metric reading to a float.

    Handles both Airthings-style ``{"value": 45, "unit": "%"}`` dicts and
    Hubitat-style scalar readings. Returns None if the value cannot be
    interpreted numerically.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict):
        raw = raw.get("value")
        if raw is None or raw == "":
            return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def extract_metric_from_status(status: Dict[str, Any], status_key: str) -> float | None:
    """Pull a single metric value out of a status_json dict.

    Looks at the top-level key, then falls back to ``attributes.<key>`` to
    match the pattern Hubitat devices use for humidity and illuminance.
    """
    val = coerce_metric_value(status.get(status_key))
    if val is not None:
        return val
    attrs = status.get("attributes")
    if isinstance(attrs, dict):
        return coerce_metric_value(attrs.get(status_key))
    return None
