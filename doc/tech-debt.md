# Technical Debt Review

Reviewed against the current `main` checkout and the open GitHub issues on
2026-06-21. This report tracks durable project work as GitHub issues; see
`AGENTS.md`.

## Executive Summary

The next major work should be:

1. Rewrite the rules system around typed rule inputs and returned device
   settings.
2. Build the map as a real application feature, not a static prototype.
3. Stabilize operations: service ownership, deployment of server files, restart
   docs, backups, and credentials.
4. Preserve diagnostic status data across retention cleanup.
5. Reduce route/data-layer coupling so features are easier to test without
   patching integrations.

The repo has made good progress on schema management, Pydantic contracts,
calculated FCU temperatures, set ranges, room metadata, and screenshot-based UI
review. The main remaining debt is architectural: the important workflows are
still hard to reason about because rules, data access, live integrations,
operations, and UI prototypes are coupled in broad modules.

## Highest Priority

### 1. Rewrite the rules system

Current state:

- `bin/rules.py` is executable Python that mutates global variables and calls
  injected functions such as `set_drive()` and `set_fan_speed()`.
- `app/rules_engine.py` builds global dictionaries from device names, time
  fields, AQI, and helper functions, then executes rules with `exec()`.
- Rule preview and real rule execution use similar but separate injected
  functions.
- Current rule helpers expose `get_temp(device_id)` and `get_fcu_temp(device_id)`,
  which is useful, but rules are still not explicit about the device being
  modified or the environmental context they consume.

Recommended direction:

- Define Pydantic models for rule inputs and outputs:
  - `DeviceRuleState`: device id, name, type, raw status, current settings,
    effective room temperature, raw FCU temperature, disabled state.
  - `EnvironmentState`: time, outdoor AQI, indoor air-quality summaries, weather
    if needed.
  - `DeviceSettings`: optional desired drive, fan speed, mode, set range, notes,
    and explanatory rule id/name.
- Make each rule a pure function:

  ```python
  def kitchen_erv_rule(device: DeviceRuleState, env: EnvironmentState) -> DeviceSettings:
      ...
  ```

- Have the engine calculate a plan first, then apply it through the same command
  path used by manual UI controls.
- Store the fired rule name and reason in the changelog and surface it in the
  main display Notes field.
- Keep previews by running the same pure functions against simulated
  `EnvironmentState`, instead of executing the rule file in a separate preview
  namespace.

Relevant issues: #118, #127, #88, #107, #5, #1.

### 2. Productize the map

Current state:

- The database and API already support `rooms.map_json`, device room assignment,
  and `RoomMap` validation.
- `app/static/map/map.html` and `map0.html` are standalone prototypes, not Flask
  pages.
- Both prototype map files currently have a JavaScript syntax error: the
  `dungeon` region is missing a comma before `bamboo`.
- The prototypes use rectangular boxes rather than the polygon model documented
  in `doc/calculated-temperatures-and-rooms.md`.
- The map is not connected to `/api/v1/rooms`, `/api/v1/status`, or navigation.

Recommended direction:

- Add a Flask route and Jinja template for `/map`.
- Render `doc/basistech_floorplan.png` or the static copy as the base image.
- Load room polygons from `/api/v1/rooms`; do not keep hard-coded regions in a
  standalone HTML file.
- Overlay current room/device state from `/api/v1/status`.
- Provide an edit mode that writes room polygons and assignments through
  existing room APIs.
- Replace the static prototype files once the real route exists.

Relevant issues: #32, #143, #144.

## Reliability and Operations

### 3. Service account, deploy ownership, and server-file deployment

Current state:

- `etc/air_basistech_net.service` still runs as `User=simsong` and `Group=simsong`
  while using `/home/air/temperature-bot`.
- `etc/slg1_basistech_net.service` uses `/home/simsong/temperature-bot`.
- `etc/deg1_basistech_net.service` uses `/home/deg/temperature-bot`.
- `make deploy` assumes `/home/air/temperature-bot` and `/var/db/temperature-bot.db`,
  but server files still require manual placement.
- `doc/deg-progress-notes.md` still contains open questions about syncing nginx
  and systemd files.

Recommended direction:

- Choose one production service account, likely `air`, and make ownership,
  systemd units, cron/runner setup, and deploy paths match it.
- Add Makefile targets to install or validate nginx/systemd files non-
  interactively.
- Document the restart and new-machine procedure in a real operations doc, then
  retire the relevant parts of `deg-progress-notes.md`.

Relevant issues: #76, #31, #44, #30.

### 4. Backups and secrets

Current state:

- `make deploy` backs up the production SQLite DB before migrations.
- `make monthly-backup` copies `/var/db/temperature-bot.db`.
- There is no complete documented backup/restore procedure for the DB plus
  `temperature-bot-config.yaml` and other credentials.

Recommended direction:

- Write `doc/operations.md` with backup, restore, restart, new-machine setup,
  service-account ownership, and credential inventory.
- Add a restore drill using a temporary DB path, not the production DB.
- Decide whether config/secrets backup belongs in Bitwarden, server backup, or
  another store.

Relevant issue: #42.

### 5. Preserve status JSON during retention cleanup

Current state:

- `bin/runner.py:combine_temp_measurements()` compresses old `devlog` rows into
  averaged rows that include only `device_id`, `logtime`, `duration`, and
  `temp10x`.
- This drops `status_json`, which causes long-running alert details to disappear
  after cleanup.
- `app/db_alerts.py` has a fallback to find the latest earlier status row, but
  that is a workaround, not preservation.

Recommended direction:

- During compression, preserve a representative `status_json` per device and
  interval, preferably the newest non-null payload in the bucket.
- Consider skipping compression for rows with important status changes, or add a
  separate status-history table if exact status timelines matter.

Relevant issue: #56.

## Architecture and Maintainability

### 6. Split `app/db.py` responsibilities

Current state:

- `app/db.py` is a very broad module covering connection setup, schema
  validation, request-time temporal parsing, device status assembly, room
  metadata, calculated temperatures, chart queries, AQI/weather response
  assembly, changelog, notes, rules disable state, and more.
- It imports Flask `request` and integration modules such as `ae200`,
  `airquality`, and `weather`.
- This makes database helpers depend on web request state and live integration
  behavior.

Recommended direction:

- Move request parsing out of `db.temporal_quantification()` and into route or
  request utility code.
- Split focused modules for rooms, calculated temperatures, time-series queries,
  changelog, and rule-disable state.
- Keep SQLite functions explicit about inputs and outputs.
- Continue using Pydantic models at module boundaries.

Relevant issue: #127.

### 7. Reduce route-level integration patching in tests

Current state:

- Many route tests patch Hubitat, AE-200, weather, and AQI calls at module
  boundaries.
- Browser tests are skipped in GitHub Actions and run local Flask servers on
  fixed ports.
- Simulators exist for AE-200, Airthings, and AQICN, but not every external
  integration path has a clean local adapter.

Recommended direction:

- Add explicit integration adapter interfaces where route and runner code need
  hardware/network data.
- Prefer local simulator-backed adapters over scattered mocks.
- Keep browser tests for real browser behavior only; use Flask test-client and
  JS unit tests for everything else.

Relevant issues: #127, #88.

### 8. Friendly names, rooms, and metadata administration

Current state:

- Display-name normalization exists in `app/display_names.py`.
- Room assignment has API support.
- There is no productized page for assigning friendly names, rooms, sensors, and
  FCUs.

Recommended direction:

- Build an admin metadata page for devices, rooms, display names, and FCU/source
  assignments.
- Decide whether friendly names are stored locally, read from Hubitat labels, or
  both.
- Make the map editor reuse this metadata rather than creating a separate
  mapping system.

Relevant issues: #143, #144.

## User-Facing UI Debt

### 9. Chart gaps for missing data

Current state:

- Time-series chart code sends contiguous ECharts line series from available
  data points.
- There is no gap insertion based on elapsed time or missing buckets.

Recommended direction:

- Add a server-side or shared client-side gap policy for time-series data.
- Insert null points or split series when the gap exceeds the threshold.
- Apply consistently to temperature, lighting, AQI, and metric charts.

Relevant issue: #117.

### 10. Remaining GUI cleanup

Current state:

- Some GUI issues are complete, such as chart `Clear All` and temperature unit
  preference.
- Remaining items include chart layout, air-quality selector hover text,
  mode/section semantics, and old CSV shortcut cleanup.

Recommended direction:

- Close completed sub-items in issue comments or split remaining items into
  smaller issues.
- Keep changes near the affected chart or dashboard files.

Relevant issues: #25, #5.

### 11. FCU history and diagnostics display

Current state:

- Temperature charts support raw and calculated temperature.
- Per-metric charts support air-quality metrics.
- There is no single FCU history view that shows room temp, FCU temp, mode, fan
  speed, drive, and diagnostic/error state together.
- Alert details expose raw status fields, but there is not yet a complete
  user-facing error-code/message treatment.

Recommended direction:

- Add an FCU-focused chart or device timeline that combines temperature,
  fan/mode/drive status, set point/range, and alerts.
- Decode or document AE-200 error fields before displaying them as user-facing
  messages.

Relevant issues: #62, #51.

### 12. Control vocabulary and manual override UX

Current state:

- FCU mode controls exist for `FAN`, `COOL`, and `HEAT`.
- Open issue #142 asks for `dry` mode, which is not represented in the current
  `ModeControl` type.
- Manual rule-disable controls use increment/decrement UI; issue #89 asks for
  an arbitrary number of hours/days.
- Some older issues still ask for clearer Mode/Drive/Power vocabulary and
  separate sections for air handlers and ventilation.

Recommended direction:

- Add `DRY` mode only after confirming the AE-200 protocol value and simulator
  payload behavior.
- Replace or supplement disable increments with explicit duration entry.
- Keep ERV/ventilation and FCU/air-handler terms consistent across templates,
  rules, API fields, and docs.

Relevant issues: #142, #89, #5.

## Lower Priority or Decision-Dependent

### 13. Dependency manager migration

Current state:

- The project uses Poetry 2.1.3 throughout `pyproject.toml`, `poetry.lock`,
  Makefile targets, and CI.
- Open issue #129 asks to migrate to `uv`.

Recommendation:

- Do not make this a prerequisite for rules or map work.
- If migrated, do it as a single tooling PR that updates Makefile, CI,
  documentation, and lockfile together.

Relevant issue: #129.

### 14. ClickHouse and long-term storage

Current state:

- SQLite remains the application DB for development and production.
- Issue #1 still lists moving to ClickHouse, but #33 was closed as completed.
- Current schema/migration work is SQLite/Flyway-centric.

Recommendation:

- Treat ClickHouse as a separate product decision, not background tech debt.
- If long-term analytics outgrow SQLite, design an export/warehouse path rather
  than replacing the operational database first.

Relevant issue: #1.

## GitHub Issue Triage

### Close now

- #121, "Add a computed temperature to FCU temperature": current code has FCU
  Temp and Room Temp columns, weighted source multipliers, default weights,
  10-minute staleness, popup editing, changelog entries, calculated chart mode,
  set ranges, and rules helpers.
- #35, "`having the graph button display just the graph for that item.`": chart
  device filtering works via `?device_ids=...`, UI links use that path, and the
  chart has Select All / Clear All controls.

### Consider closing after this report is accepted

- #22, "Migrate the answers of these questions to design documentation.": the
  README, `CLAUDE.md`, `.github/copilot-instructions.md`, SQL migration doc,
  frontend rendering strategy, calculated-temperature doc, and this report now
  answer the major architecture, local-run, API, schema, and workflow questions.
  Close it if this level of documentation is sufficient; keep #30 open for the
  remaining operations/startup doc cleanup.

### Keep open

- #144, #143, #142, #129, #127, #118, #117, #107, #89, #88, #76, #62, #56,
  #51, #44, #42, #32, #31, #30, #25, #5, #1.

These still represent incomplete features, operational gaps, or architectural
work that is visible in the current source.

## Suggested Next Sequence

1. Write the rules-system design doc and implement the typed rule input/output
   shell without changing behavior.
2. Move the current two ERV rules into pure functions and make rule preview use
   the same function path as execution.
3. Add rule firing metadata to changelog/main display.
4. Build the `/map` route using existing room APIs and floorplan assets.
5. Add `doc/operations.md` and service-account/deploy-file tooling.
6. Fix `status_json` retention during cleanup.
