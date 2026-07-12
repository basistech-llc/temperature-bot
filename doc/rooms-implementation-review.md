# Rooms Implementation Review

Reviewed on 2026-06-30 against the local checkout, rooms-related
documentation/source, open GitHub issues, and the read-only local DB copy at
`var/db/temperature-bot.db`.

## Current State

The repo has a partial rooms implementation. The durable data model exists, but
the product surfaces are still split between database-backed room metadata and
hardcoded Kitchen/Hickory dashboard configuration.

Implemented:

- Flyway migration `V3__rooms_and_fcu_temp_sources.sql` creates `rooms`,
  `devices.room_id`, and `fcu_temp_sources`.
- `app/models.py` defines `Room`, `RoomMap`, `MapPoint`, and
  `DeviceRoomControl` Pydantic models.
- `/api/v1/rooms`, `/api/v1/rooms/<room_id>`, and
  `/api/v1/update_device_room` can create/update rooms and assign devices.
- `/api/v1/status` includes `room_id` and `room_name` when devices are assigned.
- FCU calculated room temperatures and source multipliers are documented and
  implemented.
- `/devices` can edit display name, device type, rules state, and notes.
- `/kitchen` and `/hickory` render room-specific dashboards using
  `app/room_config.py`.

Not yet implemented:

- The persistent `rooms` table does not drive navigation, room dashboards, map
  rendering, or the device metadata editor.
- The local DB copy currently has 0 rows in `rooms` and 0 of 45 devices assigned
  to a room.
- `/devices` receives `room_id` and `room_name` from `db.get_device_metadata()`
  but does not show or save room assignments.
- Room dashboard membership is hardcoded by exact device names in
  `app/room_config.py`, not by `devices.room_id`.
- Room control APIs are hardcoded under `/api/v1/hickory/...`.
- `room_dashboard.js` is also hardcoded to `/api/v1/hickory/room_status`,
  `/api/v1/hickory/dimmer`, `/api/v1/hickory/wall_light`, and
  `/api/v1/hickory/tv`.
- The map exists only as standalone static prototypes under `app/static/map/`;
  it is not a Flask page, is not linked from navigation, and does not load room
  polygons or status data from APIs.
- Both static map prototypes have a JavaScript syntax error: the `dungeon`
  region is missing a comma before `bamboo`.

## Open Issues

Directly rooms-related:

- #32, "Overlay map": build an HVAC status map overlay.
- #143, "page to assign a friendly name to each sensor, room and FCU name."
- #144, "assign everything to a room".
- #152, "hickory dashboard design".
- #157, "Use per-device API calls in hickory_room_status".
- #158, "Generalize hardcoded /hickory/ API routes for any room".

Related or dependent:

- #153, "verify that new hubitat sensors are automatically added".
- #127, "Reduce route/data-layer coupling and test patching around external
  integrations".
- #107, "add presence table" for Hickory motion-based behavior.
- #62, "Create FCU graph that shows room temp, fcu temp, fcu mode and fcu fan".

## Work Needed

### 1. Make the persistent room model the source of truth

Use the `rooms` table and `devices.room_id` as the canonical room assignment
model. Keep `app/room_config.py` only for room-specific control hardware that is
not yet represented in the database, such as Hickory TV/lights.

Acceptance criteria:

- All real rooms exist in `rooms`.
- Every device that belongs to a physical room has `devices.room_id` set.
- `/api/v1/status` and `/api/v1/devices` expose enough room data for UI and
  admin pages without separate hardcoded lists.
- There is a documented way to bootstrap or edit room assignments without
  one-off SQL against production.

### 2. Add room assignment to the metadata admin UI

Extend `/devices` or add a focused `/rooms` admin page so maintainers can manage
rooms, device display names, device types, FCU names, sensor names, and room
assignments in one place.

This closes the real gap behind #143 and #144. The backend already has most of
the APIs, but there is no productized workflow.

Acceptance criteria:

- Room list is loaded from `rooms`.
- Devices can be assigned to a room or cleared from the UI.
- New rooms can be created and renamed without direct SQL.
- Duplicate room names and invalid room ids produce clear errors.
- Tests verify actual persistence in SQLite through the Flask test client.

### 3. Productize `/map`

Replace the static map prototypes with an application route.

Recommended shape:

- Add `/map` in `routes_web.py` and a Jinja template.
- Add a small `map.js` module for canvas/SVG interaction.
- Use `app/static/map/basistech_floorplan.png` as the base image.
- Load polygons from `/api/v1/rooms`.
- Load current device/room state from `/api/v1/status`.
- Link `/map` from the Rooms menu or Deep Dive menu.
- Remove or archive `map.html` and `map0.html` after the real page exists.

Acceptance criteria:

- The map uses the documented `RoomMap.polygon` format, not hardcoded
  rectangles.
- Rooms without polygons are visible in an edit/admin list.
- The map can show current HVAC/temperature status by room.
- Tests cover the route, initial HTML contract, JSON loading contract, and
  polygon rendering helper logic.

### 4. Add map edit mode

The existing prototypes are useful as a sketch for drawing regions, but the real
editor should write the documented API model.

Acceptance criteria:

- A maintainer can add/edit a polygon for a room.
- Edits are saved through `PATCH /api/v1/rooms/<room_id>`.
- Coordinates are image-relative and survive resize.
- Invalid polygons/colors are rejected by the Pydantic model.

### 5. Generalize room dashboards

Keep `/hickory` and `/kitchen` working, but move toward one room dashboard
renderer addressed by room key or room id.

Acceptance criteria:

- A new room dashboard does not require copy-pasting route functions.
- Dashboard device membership can come from `devices.room_id`, with temporary
  config overrides only where needed.
- Existing `/hickory` and `/kitchen` URLs remain compatible.
- The Rooms menu is generated from configured or database-backed rooms instead
  of hardcoding two links in `base.html`.

### 6. Generalize room control APIs

Address #158 by adding generic room-control endpoints, for example
`/api/v1/room/<location>/room_status`, `/dimmer`, `/wall_light`, and `/tv`, or a
similar consistent route shape.

Acceptance criteria:

- Unknown rooms return clear 404-style JSON errors.
- Rooms without a given control return a clear unsupported-control error.
- Existing Hickory endpoints either remain as compatibility wrappers or are
  redirected internally without breaking current clients.
- `room_dashboard.js` derives endpoint URLs from template data instead of
  hardcoding Hickory.
- Control request bodies use Pydantic models instead of ad hoc dictionaries.

### 7. Fix Hickory room status reads

Address #157 before or while generalizing controls. `hickory_room_status()`
currently reads all Hubitat devices and filters locally; the issue says the
all-devices endpoint may omit current attributes.

Acceptance criteria:

- Room status reads dimmer and light state with per-device
  `hubitat.get_device_info(device_id)` calls.
- A failure for one configured device does not fail the whole status response.
- Tests cover partial device failures and missing devices.
- The old behavior for successful Hickory status remains unchanged.

### 8. Finish the Hickory dashboard design items

Issue #152 is partially reflected in the current template, but it is not
complete.

Already reflected:

- The "Hickory HVAC Control" style header is gone.
- The "Room Controls" and "Temperature Sensors" captions are gone.
- Room controls render above the HVAC cards.

Still needed:

- Rename "ERV Restrooms" to "Restroom Ventilation" in the user-facing UI.
- Rename "Restrooms/BOH" to "Restroom Heating and Cooling" in the user-facing UI.
- Add/show the requested "Dungeon Main" sensor tile alongside Hickory and Dungeon
  Cage, once the authoritative device name is confirmed.
- Prefer solving the labels through display-name metadata, not template-specific
  string substitutions.

### 9. Make sensor discovery and room assignment operational

Issue #153 matters because room dashboards currently depend on exact static
sensor names. New Hubitat sensors can exist but not appear in dashboards unless
config/code is updated.

Acceptance criteria:

- Newly discovered Hubitat sensors get a device row or a clear pending-metadata
  state.
- Maintainers can assign discovered sensors to rooms in the metadata UI.
- Room dashboards can include sensors assigned to the room without adding names
  to `app/room_config.py`.

### 10. Improve FCU room-temperature administration

The calculated room temperature work is mostly implemented, but source selection
is still per-FCU through the main dashboard popup. Most FCUs in prior review
data were still using default self-only weights.

Acceptance criteria:

- There is an admin workflow to review FCU source multipliers by room.
- Source candidates are grouped or filtered by room.
- The UI makes it obvious when an FCU is still using the default self weight.
- The calculated/raw temperature distinction stays explicit in labels and docs.

## Suggested Sequence

1. Implement #157 first because it is a correctness fix for the existing Hickory
   controls.
2. Implement #143/#144 together by extending the metadata admin UI to manage
   rooms and assignments.
3. Seed or assign actual rooms/devices through that UI or a documented
   non-production-tested workflow.
4. Build `/map` on top of `/api/v1/rooms` and `/api/v1/status`.
5. Generalize dashboard/control routes once the persistent room assignments are
   populated enough to drive real pages.
6. Finish the remaining Hickory dashboard design items through metadata-backed
   display names.

## Testing Guidance

- Use the Makefile targets; do not run underlying test commands directly.
- Prefer SQLite-backed Flask test-client tests for room CRUD, device-room
  assignment, and metadata UI persistence.
- Use JavaScript unit tests only for real client logic such as endpoint
  selection, polygon coordinate conversion, and render helpers.
- Avoid pro-forma coverage tests. The useful tests here are persistence,
  validation, compatibility of existing Hickory/Kitchen URLs, and map coordinate
  behavior.
- Avoid mocking except where live Hubitat hardware is unavoidable; where possible
  introduce a small adapter/simulator seam as part of #127.
