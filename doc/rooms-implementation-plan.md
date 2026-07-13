# Rooms Implementation Plan

Approved on 2026-07-13 after review of the current implementation, every open
GitHub issue, and the open local Beads queue.

GitHub issue #144 is the canonical umbrella. The local implementation epic is
Beads `hvac-9re`.

## Product Decisions

- Every FCU owns one room.
- A room defaults to the FCU display name and can be renamed.
- Automatically generated duplicate names use numbered suffixes: `Name (2)`,
  `Name (3)`, and so on.
- An operator rename must reject a duplicate room name.
- A newly discovered FCU automatically creates and joins its room.
- Every physical non-ERV device is eligible for room assignment.
- ERVs and `INTERNAL` pseudo-devices such as `rules_engine` and `rules_master`
  remain outside the room model.
- `room_id IS NULL` represents the virtual **Unassigned** room group. It is not
  a special row in `rooms` and cannot be renamed.
- Existing FCUs are assigned to newly created rooms. Existing physical
  non-ERV, non-FCU devices begin in Unassigned.

## Sensor Matrix

The main-page Air Quality matrix remains one table with one shared header.

- Rooms appear alphabetically, even when a room has no displayed sensors.
- Unassigned appears as a group in the same alphabetical sequence.
- A thick separator precedes each room, with its room name overlaid at the
  left.
- Sensor rows are draggable between room groups.
- A successful drop persists immediately.
- The browser moves a row optimistically, then restores it and reports an
  error if persistence fails.
- Right-clicking a room name opens its rename dialog.
- Long-pressing the same room name performs the equivalent action on a touch
  display.
- A successful rename re-sorts the room groups without requiring a page
  reload.

## Shared Metric Mechanism

Room membership is the single eligibility mechanism for both dashboard
grouping and FCU room calculations. Metric-specific aggregation is layered on
top of that shared selection.

### Temperature

- Preserve the existing `fcu_temp_sources` multipliers.
- A source contributes only while it is assigned to the FCU room.
- Moving a source out of the room makes its stored multiplier inactive; moving
  it back restores that multiplier.
- The FCU inlet temperature is subject to the same room and staleness rules as
  every other temperature source.
- Current and historical calculated series use current room membership and
  current weights, matching the existing current-weight history contract.
- Historical series must preserve visible gaps when every eligible source is
  stale. The chart must not connect two valid points across a stale interval
  and imply that intermediate data existed.

### Humidity

- Use every in-room humidity source with a current reading.
- Compute the equal-weight arithmetic mean; humidity has no multiplier table.
- Display the result as an integer percent.
- Display `--` when no non-stale humidity value exists.

### Staleness and Formatting

- Temperature and humidity calculations never use stale values.
- Both use the existing 10-minute source cutoff.
- Celsius temperatures retain decimal precision.
- Fahrenheit temperatures display as whole degrees.

## Architecture and Refactoring

### Persistence and discovery

Refactor `app/db.py` and the device discovery paths to provide an idempotent,
transactional room reconciliation operation. Add a Flyway migration for any
new constraints, then regenerate `etc/schema.sql` with `make schema`.

Discovery must persist a valid `device_type`; it must not depend on the V6
one-time backfill. Room creation and FCU assignment must be atomic.

### Shared room metric service

Add `app/room_metrics.py` as the typed service boundary for:

- room membership and device eligibility;
- latest-reading lookup;
- temperature and humidity extraction from supported payloads;
- the shared stale cutoff; and
- typed source and aggregate results.

Keep raw SQLite queries in `app/db.py`. Route code passes explicit inputs to
the service; the service does not read Flask request state. This is a scoped
step toward the layering requested by GitHub #127.

### Typed API contracts

Refactor `app/models.py`, `app/routes_api.py`, and their tests so room listing,
assignment, rename, and calculated humidity use Pydantic request and response
models.

- Reject unknown fields on new or changed control requests.
- Reject assignments for ERV and `INTERNAL` devices.
- Do not allow the sensor-assignment endpoint to move an FCU away from its
  owned room.
- Return a conflict response for duplicate rename targets.
- Make successful assignment visible to the next status and calculation
  request.

### Server-rendered grouping

Refactor `app/routes_web.py` to build typed room-group view models. Refactor
`app/templates/index.html` and `app/static/style.css` to render the separators,
empty rooms, Unassigned group, and draggable sensor rows while preserving
metric links, notes, thresholds, and table update summaries.

### Browser interactions

Add a self-contained `app/static/room_matrix.js` for pointer drag/drop,
optimistic persistence, rollback, context-menu rename, and touch long-press.
Test pure gesture and state-transition logic with Node through the Makefile.
Do not add Playwright for this feature.

Refactor `app/static/unit_speed.js` so FCU room humidity comes from the API and
the Room Editor consumes the same in-room source contract. Do not duplicate
humidity aggregation in the browser.

## Beads Work Breakdown

| Bead | Work | Blocks on |
| --- | --- | --- |
| `hvac-9re` | Implement rooms as canonical FCU and sensor topology | — |
| `hvac-9re.1` | Bootstrap room topology and FCU discovery lifecycle | — |
| `hvac-9re.2` | Refactor shared room metric source selection | `.1` |
| `hvac-9re.3` | Apply room membership to FCU temperature and room humidity | `.1`, `.2` |
| `hvac-9re.4` | Expose typed room topology and assignment APIs | `.1`, `.3` |
| `hvac-9re.5` | Render the Air Quality matrix by room | `.1`, `.4` |
| `hvac-9re.6` | Add sensor drag/drop and room rename interactions | `.4`, `.5` |
| `hvac-9re.7` | Refactor FCU Room Editor and dashboard value formatting | `.3`, `.4` |
| `hvac-9re.8` | Document and verify the rooms implementation | `.1`–`.7` |

Each implementation bead includes substantive SQLite, Flask-client, or pure
JavaScript logic tests. Tests run through Makefile targets and must not modify
`var/db/temperature-bot.db`.

## Issue Audit

### Direct canonical work

- [#144, assign everything to a room](https://github.com/basistech-llc/temperature-bot/issues/144)
  is the umbrella issue implemented by this plan.
- [#153, verify that new Hubitat sensors are automatically added](https://github.com/basistech-llc/temperature-bot/issues/153)
  is covered by typed discovery, Unassigned placement, and automatic FCU room
  creation.
- [#127, reduce route/data-layer coupling](https://github.com/basistech-llc/temperature-bot/issues/127)
  is partially advanced by the typed `room_metrics` service. The broader
  request parsing and integration refactor remains outside this plan.
- [#62, create an FCU graph with room and FCU state](https://github.com/basistech-llc/temperature-bot/issues/62)
  depends on the room-temperature semantics defined here. This plan does not
  add the combined graph.
- [#117, do not draw through missing chart data](https://github.com/basistech-llc/temperature-bot/issues/117)
  requires calculated room-temperature history to preserve stale gaps rather
  than merely omitting samples and allowing the chart to connect across them.

### Downstream room consumers

- [#32, overlay map](https://github.com/basistech-llc/temperature-bot/issues/32)
  should consume the canonical rooms and assignments created here; map UI is
  outside this plan.
- [#107, add presence table](https://github.com/basistech-llc/temperature-bot/issues/107)
  can later use room-assigned motion sensors; presence storage and rules remain
  separate work.
- [#152, Hickory dashboard design](https://github.com/basistech-llc/temperature-bot/issues/152)
  can later replace exact-name sensor membership with room membership. The
  current plan changes the main Air Quality matrix, not room dashboard layout.
- [#158, generalize hardcoded Hickory APIs](https://github.com/basistech-llc/temperature-bot/issues/158)
  should reuse canonical room identity later. Generic room control endpoints
  remain out of scope.
- [#157, use per-device calls in Hickory room status](https://github.com/basistech-llc/temperature-bot/issues/157)
  remains an independent Hubitat correctness fix and is not blocked by this
  plan.

### Historical and presentation overlap

- [#143, friendly names for sensors, rooms, and FCUs](https://github.com/basistech-llc/temperature-bot/issues/143)
  is closed. This plan reuses its display-name work and adds room rename UI.
- [#25, GUI tweaks](https://github.com/basistech-llc/temperature-bot/issues/25)
  already established the persistent C/F preference that the new formatting
  must preserve.
- [#51, explain recorded AE-200 temperatures](https://github.com/basistech-llc/temperature-bot/issues/51)
  reinforces the need to keep FCU inlet and calculated Room Temp labels
  explicit; broader AE-200 error reporting remains separate.

### Relevant open local Beads constraints

- `hvac-a9u`: discovery must enforce `device_type` for new devices.
- `hvac-obp`: new and changed room control models must reject unknown fields.
- `hvac-kag` and `hvac-9ai`: production Flyway work needs a quiesced writer and
  a consistent backup/rollback path.
- `hvac-7mx`: use pure JavaScript tests, not new local-only Playwright tests.
- `hvac-sep`: exercise the actual Hubitat simulator discovery payload where it
  provides substantive coverage.
- `hvac-hem`: humidity threshold coloring is separate from calculating and
  displaying integer room humidity.
- `hvac-1mz` and `hvac-8tp`: these mirror GitHub #157 and #158 and remain
  outside the implementation scope above.

## Delivery Sequence

1. Implement and verify topology bootstrap and discovery.
2. Extract the shared room metric service.
3. Apply room eligibility to current and historical temperature and to room
   humidity.
4. Harden typed room APIs.
5. Render the grouped matrix.
6. Add drag/drop and rename behavior.
7. Refactor the Room Editor and value formatting.
8. Update final documentation and run the relevant Makefile quality gates.

The production assignment bootstrap should run only after the deployment path
has taken a consistent database backup and prevented concurrent writers for the
duration of migration.
