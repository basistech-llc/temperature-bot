"""
Helpers for computing human-friendly device display names.

Goals:
- Centralize all transformations of raw device names used in the UI.
- Make it easy to tweak how names are presented without touching every caller.

This module should be the ONLY place that knows about:
- Stripping vendor prefixes (e.g. ``"Airthings "``)
- Dropping location suffixes like ``" on Somerville Greenhouse"``
- Preferring Hubitat labels over raw device names when present
"""

from __future__ import annotations

from typing import Optional


_AIRTHINGS_PREFIX = "Airthings "
_ON_DELIMITER = " on "


def _strip_airthings_prefix(name: str) -> str:
    """Remove the leading ``'Airthings '`` prefix, if present."""
    if name.startswith(_AIRTHINGS_PREFIX):
        return name[len(_AIRTHINGS_PREFIX) :]
    return name


def _strip_on_clause(name: str) -> str:
    """
    Elide trailing ``' on XYZ'`` clauses from device names.

    Examples
    --------
    - ``'Greenhouse Sensor West on Somerville Greenhouse'`` → ``'Greenhouse Sensor West'``
    - ``'Lobby Sensor'`` → unchanged
    """
    idx = name.find(_ON_DELIMITER)
    if idx == -1:
        return name
    # Only keep the part before " on "
    return name[:idx]


def display_device_name(
    raw_name: str,
    *,
    hubitat_label: Optional[str] = None,
    source: Optional[str] = None,
) -> str:
    """
    Return the canonical human-friendly display name for a device.

    Parameters
    ----------
    raw_name:
        The underlying system/DB name (e.g. from ``devices.device_name`` or Hubitat ``name``).

    hubitat_label:
        Optional Hubitat ``label`` for the device. When provided, this is preferred as the
        starting point for display, falling back to ``raw_name`` if empty.

    source:
        Optional logical source of the name; currently informational only, but kept for
        future extension (e.g. special handling per source type: ``'hubitat'``,
        ``'airthings'``, ``'ae200'``, etc.).

    Notes
    -----
    Current transformations (in order):
    - Prefer ``hubitat_label`` over ``raw_name`` when provided.
    - Strip the ``'Airthings '`` vendor prefix.
    - Elide ``' on '`` and everything after it to remove verbose location suffixes.
    """
    # Currently informational only; keep reference so linters know it's intentional.
    _ = source
    base = (hubitat_label or raw_name or "").strip()

    # Strip vendor-specific prefixes we don't want in most UI labels.
    base = _strip_airthings_prefix(base)

    # Apply the requested "XXX on YYY" elision globally, since this pattern shows up
    # in multiple device sources and is always distracting for users.
    base = _strip_on_clause(base)

    return base


def append_display_icon(label: str, icon: str) -> str:
    """Append one presentation icon unless the label already ends with it."""
    return f"{label} {icon}" if icon and not label.rstrip().endswith(icon) else label


__all__ = ["append_display_icon", "display_device_name"]
