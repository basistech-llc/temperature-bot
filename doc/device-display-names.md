## Device display naming strategy

This document summarizes how device names are derived and presented in the UI, and where to change behavior when we want to tweak how names look.

The goals are:

- **Single point of control** for human-facing names.
- **Stable “system” names** for configuration, matching, and debugging.
- **Predictable, documented transforms** (e.g. eliding verbose suffixes).

---

### Sources of truth for names

- **Database (`devices.device_name`)**
  - Primary persistent identifier for HVAC units and sensors.
  - Used wherever we need an exact, stable name (room configuration, alerts, logs, debug tools).

- **Hubitat**
  - Each device has a `name` and an optional `label`.
  - `name` is the stable identifier; `label` is usually more human-friendly.
  - We construct a `name -> label` map via `hubitat.get_name_to_label()`.

- **AE-200**
  - Devices have an `id` and `name`.
  - Used primarily for debug/admin views and for correlating with the AE-200 controller.

- **Airthings / Air-quality devices**
  - Indoor Airthings monitors are stored in the DB and exposed via `db.get_all_device_aqi`.
  - Their `device_name` values sometimes carry vendor prefixes such as `Airthings `.

---

### Central helper: `display_device_name`

All **human-facing labels** should go through `app.display_names.display_device_name` rather than doing ad-hoc string manipulation in routes or templates.

Signature:

```python
from app.display_names import display_device_name

display = display_device_name(
    raw_name,
    hubitat_label=optional_label,
    source="hubitat" | "db" | "airthings" | "ae200" | None,
)
```

Current behavior:

- **Start from the best available label**
  - Prefer `hubitat_label` when provided, otherwise `raw_name`.
- **Strip vendor prefixes**
  - Remove leading `Airthings ` when present.
- **Elide `" on "` suffixes**
  - For names of the form `XXX on YYY`, drop the suffix entirely:
    - `Greenhouse Sensor West on Somerville Greenhouse`  
      → `Greenhouse Sensor West`.
  - This is applied generically because this pattern appears across multiple device sources and is consistently noisy for end-users.

To change how names are displayed across the app, edit **only** `display_device_name` (or the private helpers in `app/display_names.py`).

---

### Where we use display names vs raw names

**User-facing pages (prefer display names)**

- **Main index (`index.html`) – Air Quality section**
  - Route: `read_index` in `routes_web.py`.
  - For each device row we compute:
    - `device_label = display_device_name(raw_name, hubitat_label=hubitat_label, source="hubitat")`.
  - Template shows `device_label` as the primary label and uses the raw `device_name` in the tooltip.

- **Room dashboards (`room_dashboard.html`) – Hubitat sensors**
  - Route: `_render_room_dashboard_with_data` in `routes_web.py`.
  - For each `sensor` from Hubitat:
    - `sensor["display_name"] = display_device_name(sensor["name"], hubitat_label=sensor["label"], source="hubitat")`.
  - Template uses `sensor.display_name` as the visible sensor name, with `sensor.name` as the tooltip.

- **Air Quality page (`air-quality.html`)**
  - Route: `air_quality` in `routes_web.py`.
  - For each row in `airmon`:
    - `row["display_name"] = display_device_name(row["device_name"], source="airthings")`.
  - Template displays `row.display_name`, falling back to `row.device_name` if needed.

- **Temperature charts (`/api/v1/temperature` + `chart_support.js`)**
  - API handler: `get_temperature` in `routes_api.py`.
  - For each series:
    - The series `name` is rewritten via `display_device_name(raw_name, hubitat_label=hubitat_label, source="hubitat")`.
  - Chart legends and lines show this display name.

- **Chart sensor checkbox list (`chart_support.js`)**
  - API: `/api/v1/status`.
  - Handler: `get_status` in `routes_api.py` attaches `display_name` to each device using `display_device_name(device_name, source="db")`.
  - The JS now uses `device.display_name || device.device_name` when building the list of sensor names for checkboxes.

**Admin / debug views (prefer raw or composite names)**

These views intentionally show system-accurate names for debugging and cross-system mapping:

- **All Devices (`debug_all_devices.html`)**
  - `/api/v1/debug/db_devices`: returns:
    - `names`: list of strings like `"name (label)"` when a matching Hubitat label exists.
    - `data`: full device dicts including raw `device_name`.
  - `/api/v1/debug/hubitat_devices`: similar `"name (label)"` representation.
  - `/api/v1/debug/ae200_devices`: raw AE-200 `name`s and device metadata.

- **Alerts (`alerts.html`)**
  - Filter dropdown and table rows use the raw `device_name` from the DB.
  - This keeps alerts easy to correlate with logs, device configuration, and AE-200 units.

- **Device log & changelog views**
  - Device header table in `device_log.html` shows `device_name` directly.
  - Changelog queries use `d.device_name as unit` for log entries.

These admin views can start using `display_device_name` in the future if we decide some transformations (like `"XXX on YYY"` elision) are also desirable there, but for now they prioritize **fidelity over brevity**.

---

### How to adopt the helper in new code

When adding a new place that shows a device/sensor name:

- **If it’s a user-facing label (dashboards, charts, filters):**
  - Use `display_device_name(raw_name, hubitat_label=..., source=...)`.
  - Keep the **raw name** available somewhere nearby (e.g. tooltip text, data attribute) for debugging and correlation.

- **If it’s an admin/debug or configuration view:**
  - Prefer the raw `device_name` (or raw Hubitat/AE-200 `name`) to avoid any ambiguity.
  - You may still show a display name alongside it if that aids readability, but don’t replace the system name entirely.

This keeps behavior consistent and ensures future naming changes only require edits in `app/display_names.py` instead of scattered string logic across templates and routes.

