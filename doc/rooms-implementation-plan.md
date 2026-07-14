# Rooms Implementation Plan

Approved on 2026-07-13 after review of the current implementation, every open
GitHub issue, and the open local Beads queue.

GitHub issue #144 is the canonical umbrella. The local implementation epic is
Beads `hvac-9re`. The plan delivers the room model in a core phase, then moves
every identified room-oriented GitHub issue onto that canonical topology. The
follow-on phase is part of the plan, but does not delay the core room release.

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

### Room-oriented consumers

After the core room release, migrate the remaining room consumers without
creating any parallel location or membership mapping:

- GitHub #32: resolve map regions through stable room identity and use shared
  room status for temperature, humidity, and FCU state. Map geometry is
  presentation data and must survive room rename.
- GitHub #62: build the combined FCU history graph from canonical calculated
  room temperature, recorded FCU temperature, mode, and fan data. Preserve the
  stale gaps required by #117.
- GitHub #152: replace exact-name sensor membership in Hickory and other room
  dashboards with persisted room assignments. Keep deliberate actuator and
  layout configuration separate from membership.
- GitHub #107: assign presence-capable devices through the same room topology,
  while keeping presence event retention and rule policy metric-specific.
- GitHub #157: correct Hickory status reads before generalizing its controls.
  The existing Bead `hvac-1mz` owns this work.
- GitHub #158: generalize the corrected Hickory control APIs around stable room
  identity after canonical room dashboards exist. The existing Bead
  `hvac-8tp` owns this work.

GitHub #127 remains broader than rooms. The room service removes route and data
coupling for this feature, but the canonical issue stays open for unrelated
routes unless its remaining acceptance criteria are completed separately.

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
| `hvac-9re.9` | Build room-backed HVAC map overlay (#32) | `.3`, `.4` |
| `hvac-9re.10` | Add combined FCU and room history graph (#62) | `.3` |
| `hvac-9re.11` | Drive room dashboards from canonical assignments (#152) | `.4`, `.7` |
| `hvac-9re.12` | Integrate presence sensors and room presence rules (#107) | `.4` |
| `hvac-1mz` | Correct Hickory per-device status reads (#157) | — |
| `hvac-8tp` | Generalize room control APIs (#158) | `hvac-1mz`, `.11` |
| `hvac-9re.13` | Verify integrated consumers and canonical issue closure | `.8`–`.12`, `hvac-1mz`, `hvac-8tp` |

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
  request parsing and integration refactor remains in the canonical issue and
  is not implied complete by the rooms release.
- [#62, create an FCU graph with room and FCU state](https://github.com/basistech-llc/temperature-bot/issues/62)
  is delivered after the core room-temperature semantics by `hvac-9re.10`.
- [#117, do not draw through missing chart data](https://github.com/basistech-llc/temperature-bot/issues/117)
  requires calculated room-temperature history to preserve stale gaps rather
  than merely omitting samples and allowing the chart to connect across them;
  `hvac-9re.3` establishes the data contract and `.10` preserves it in the
  combined graph.

### Downstream room consumers

- [#32, overlay map](https://github.com/basistech-llc/temperature-bot/issues/32)
  is delivered by `hvac-9re.9` using canonical rooms and assignments.
- [#107, add presence table](https://github.com/basistech-llc/temperature-bot/issues/107)
  is delivered by `hvac-9re.12`. Hubitat motion observations retain the
  canonical room identity they had when recorded. Current UI and rule results
  share a 15-minute presence policy and explicitly distinguish stale readings
  from rooms that have no observations.
- [#152, Hickory dashboard design](https://github.com/basistech-llc/temperature-bot/issues/152)
  is advanced by `hvac-9re.11`, which migrates room dashboard data membership.
  The GitHub issue should close only when its broader layout acceptance is also
  satisfied.
- [#158, generalize hardcoded Hickory APIs](https://github.com/basistech-llc/temperature-bot/issues/158)
  is delivered by existing Bead `hvac-8tp` after canonical dashboards exist.
- [#157, use per-device calls in Hickory room status](https://github.com/basistech-llc/temperature-bot/issues/157)
  is delivered by existing Bead `hvac-1mz` and blocks generic control API work.

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
- `hvac-1mz` and `hvac-8tp`: these mirror GitHub #157 and #158. They are reused
  directly in this plan rather than duplicated under `hvac-9re`.

## Delivery Sequence

### Phase 1: core rooms

The UI-first slice and its backend metric prerequisites are complete:

- [x] Render every room, including empty rooms and Unassigned, in one
  alphabetically grouped sensor table.
- [x] Add immediate-save mouse/touch drag and drop with optimistic rollback.
- [x] Add duplicate-safe room rename UI through right-click, touch long-press,
  and the FCU Room Editor.
- [x] Limit Room Editor candidates to the FCU room while preserving inactive
  stored weights.
- [x] Display humidity as integer percent, Celsius with decimals, Fahrenheit
  as whole degrees, and missing calculated values as `--`.
- [x] Add `make rooms-ui-demo` using a disposable database under `/tmp`.
- [x] Complete the backend room temperature and humidity calculations with
  room-filtered weights, equal-weight humidity, and explicit stale gaps.

- [x] Implement and verify topology bootstrap and discovery (`hvac-9re.1`).
- [x] Extract the shared room metric service (`hvac-9re.2`).
- [x] Apply room eligibility to current and historical temperature and to room
  humidity (`hvac-9re.3`).
- [x] Harden typed room APIs (`hvac-9re.4`).
- [x] Render the grouped matrix (`hvac-9re.5`).
- [x] Add drag/drop and rename behavior (`hvac-9re.6`).
- [x] Refactor the Room Editor and value formatting (`hvac-9re.7`).
- [x] Update core documentation and run the relevant Makefile quality gates
  (`hvac-9re.8`).

### Phase 2: canonical room consumers

- [x] Build the room-backed map (`hvac-9re.9`).
- [x] Build the combined FCU graph (`hvac-9re.10`) after its shared data
  prerequisites are complete.
- [x] Migrate room dashboards away from exact-name sensor membership
  (`hvac-9re.11`).
- [x] Add room-based presence storage, presentation, and rules
  (`hvac-9re.12`).
- [x] Correct Hickory per-device reads (`hvac-1mz`), then generalize room
  control endpoints (`hvac-8tp`).

### Phase 3: integration and issue reconciliation

- [ ] Verify rename, reassignment, Unassigned, stale-data, and missing-data
  behavior across every consumer (`hvac-9re.13`).
- [ ] Update each canonical GitHub issue with evidence. Close only the issues
  whose full acceptance criteria are satisfied; record residual work on broad
  issues such as #127 and #152.

The production assignment bootstrap should run only after the deployment path
has taken a consistent database backup and prevented concurrent writers for the
duration of migration.
