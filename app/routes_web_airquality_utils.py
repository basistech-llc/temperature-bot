"""Helpers for air-quality specific web rendering."""

import datetime
import time
from typing import Any, Optional

from .util import github_style_duration


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
