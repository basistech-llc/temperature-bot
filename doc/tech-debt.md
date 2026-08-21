# Technical Debt Review

Reviewed against the current `main` checkout and the open GitHub issues on
2026-07-14. This report tracks durable project work as GitHub issues; see
`AGENTS.md`.

## Executive Summary

The next major work should be:

1. Remove production reloader, worker-count, ownership, and debug-configuration
   hazards from the checked-in service definitions.
2. Establish typed dashboard, API, transaction, and frontend-bootstrap
   contracts before further dashboard feature work.
3. Split the large database and dashboard modules along those contracts.
4. Rewrite the rules system around typed rule inputs and returned device
   settings, with shadow evaluation before any production cutover.
5. Consolidate application settings, integration-test adapters, and duplicated
   architecture guidance.

The repo has made good progress on schema management, Pydantic contracts,
calculated FCU temperatures, set ranges, room metadata, and screenshot-based UI
review. The main remaining debt is architectural: the important workflows are
still hard to reason about because rules, data access, live integrations,
operations, and UI prototypes are coupled in broad modules.

## AI Reliability Cleanup Plan

The July 2026 review found that recent PR churn was not a collection of isolated
syntax mistakes. The same domain concepts are implemented independently in
route dictionaries, Pydantic models, Jinja, JavaScript, SQL predicates, and
systemd files. Small changes therefore require an agent or human to discover
several implicit contracts at once. The cleanup goal is to reduce the number of
places in which a correct decision can be represented.

Two GitHub milestones track this work:

- [AI Reliability - Primary Cleanup](https://github.com/basistech-llc/temperature-bot/milestone/2):
  production safety and typed, single-owner application boundaries.
- [AI Reliability - Secondary Cleanup](https://github.com/basistech-llc/temperature-bot/milestone/3):
  settings, local integration seams, and verifiably current guidance.

### Design rules for the cleanup

1. One owner per transaction, refresh loop, DOM region, and configuration value.
2. Pydantic models at application boundaries; dictionaries only for external
   payloads, with keys represented by named symbols.
3. Routes parse and serialize; services enforce policy; repositories perform
   SQL; adapters communicate with external systems.
4. Initial Jinja rendering and later JavaScript refreshes consume the same
   presentation contract.
5. Every mutation documents foreign-key, history-retention, concurrency, and
   rollback behavior.
6. Each PR changes one boundary at a time and preserves a rollback path. Do not
   combine these cleanup issues into one large rewrite.

### Primary cleanup sequence

| Phase | Issues | Deliverable | Human acceptance gate |
| --- | --- | --- | --- |
| P0: production containment | [#180](https://github.com/basistech-llc/temperature-bot/issues/180) | Production-safe systemd/Gunicorn configuration, validation, ownership, restart, and rollback documentation | Linux unit validation plus stable CPU, ping, nginx, polling, room rename, and FCU control on each deployment site |
| P1: explicit write contracts | [#182](https://github.com/basistech-llc/temperature-bot/issues/182), [#184](https://github.com/basistech-llc/temperature-bot/issues/184), [#185](https://github.com/basistech-llc/temperature-bot/issues/185) | Strict dashboard view models, one SQLite transaction owner, intentional foreign-key deletion policy, and uniform API errors | Real SQLite tests cover success, every domain conflict, rollback, history retention, and malformed requests |
| P2: service boundaries | [#183](https://github.com/basistech-llc/temperature-bot/issues/183), [#187](https://github.com/basistech-llc/temperature-bot/issues/187) | Focused repositories/services and one typed server-to-browser bootstrap contract | Status payloads, raw HTML, post-refresh DOM, query results, and runner behavior match the prior revision |
| P3: frontend ownership | [#181](https://github.com/basistech-llc/temperature-bot/issues/181) | Small dashboard feature modules with one coordinator, one polling loop, and one writer per DOM region | All manual controls and failure paths pass locally and on clone sites without duplicate requests or console errors |
| P4: rules isolation | [#186](https://github.com/basistech-llc/temperature-bot/issues/186) | Typed pure rule functions, plan-then-apply execution, identical preview/shadow/production evaluation, and recorded decision reasons | Recorded-input replay and live shadow comparison pass before a separately approved, supervised production cutover |

P0 should land before another service-file installation. P1 contracts should land
before P2/P3 decomposition so extracted modules have stable boundaries. P4 is
last because it can change live equipment and requires evidence from the new
service and test boundaries.

### Secondary cleanup sequence

| Phase | Issues | Deliverable | Human acceptance gate |
| --- | --- | --- | --- |
| S1: settings | [#188](https://github.com/basistech-llc/temperature-bot/issues/188) | One typed settings model with explicit development, test, clone, and production behavior | Effective safe configuration is visible at startup; production has no debug or reload behavior |
| S2: integration seams | [#189](https://github.com/basistech-llc/temperature-bot/issues/189) | Injected external-system adapters, simulator-backed tests, dynamic browser ports, and fewer module patches | Offline local acceptance pass and CI exercise meaningful success and failure behavior |
| S3: guidance | [#190](https://github.com/basistech-llc/temperature-bot/issues/190) | Canonical architecture/operations documents plus checks for broken links, forbidden flags, and stale assertions | A developer unfamiliar with the change can follow the test, deployment, and rollback instructions successfully |

S1 can proceed after P0 defines environment profiles. S2 should follow the P2
service boundaries. S3 is updated throughout the work and closes only after the
primary architecture is stable.

### Human test matrix

All commands are run through the Makefile.

| Change type | Required automated checks | Required human checks |
| --- | --- | --- |
| Every PR | `make check`; focused substantive tests | Review the diff against the issue's boundary and confirm rollback instructions |
| Python/data/API | `make pytest`; `make validate-migrations` for schema work | Exercise success, not-found, validation, conflict, integration-offline, and rollback paths using a temporary database |
| Dashboard/Jinja/JavaScript | `make test-js`; focused route tests; relevant screenshot target | Compare raw server HTML with the post-refresh DOM; exercise every changed control and inspect request rate/browser console |
| Services/operations | Repository service-config check plus `systemd-analyze verify` on Linux | Confirm unit identity, process tree, worker count, logging, CPU, memory, ping, nginx, restart, and rollback |
| Rules | `make pytest`, deterministic replay, simulator runner tests | Compare legacy and new plans in shadow mode; independently verify Mitsubishi state during a supervised cutover |

Tests must use temporary/Flyway-created databases or a read-only production
copy. Do not migrate or mutate `var/db/temperature-bot.db` as part of routine
validation.

### Deployment places and order

1. **Local development:** temporary SQLite database, AE-200/AQI/Airthings
   simulators, Flask test client, Node tests, and browser/screenshot checks.
2. **`deg1.basistech.net`:** first deployed observation point for application
   and unit changes. Verify logs and resource use before proceeding.
3. **`slg1.basistech.net`:** Simson's clone site. It shares the physical machine
   with `air.basistech.net`, so success here is not an independent host-capacity
   test. Watch aggregate CPU and memory as well as the clone process.
4. **`air.basistech.net`:** main site. Deployment is human-authorized and
   human-executed only, after the issue-specific gates pass. Record the prior
   commit/unit file, database backup where applicable, health evidence, and the
   exact rollback command before changing it.

Rules changes add a shadow-only stage on `deg1` and `slg1`; they must not send
commands until a human explicitly approves the production cutover. Agents are
not authorized to deploy these changes to `slg1` or `air`.

## Existing Feature and Operational Debt

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

Relevant issues: #186, #118, #127, #88, #107, #5, #1.

### 2. Complete map administration

Current state:

- `/map` is now a Flask page rendered by `app/templates/map.html` with behavior
  in `app/static/room_map.js` and substantive route/JavaScript tests.
- The page consumes room polygon and live status data instead of relying only on
  the old standalone prototypes.
- Room creation, rename, deletion, and sensor assignment are available from the
  Air Quality matrix. Remaining map work should reuse those canonical room APIs
  and semantics.

Recommended direction:

- Finish any remaining polygon edit workflow through `/api/v1/rooms`.
- Ensure map and matrix administration share typed room contracts rather than
  implementing separate naming or assignment rules.
- Remove obsolete prototypes and stale guidance after confirming they are no
  longer referenced.

The original productization issues #32, #143, and #144 are closed. New map work
should receive a narrowly scoped issue rather than reopening the old prototype
plan.

## Reliability and Operations

### 3. Service account, deploy ownership, and server-file deployment

Current state:

- The checked-in Gunicorn service units omit `--reload`, matching the manually
  corrected live production process.
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

Relevant issues: #180, #177, #76, #31, #44, #30.

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

Relevant issues: #183, #184, #127.

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

Relevant issues: #189, #127, #88.

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

- The project uses uv throughout `pyproject.toml`, `uv.lock`, Makefile targets,
  CI, deployment tooling, and documentation.
- `make dependency-check` verifies the lockfile and prevents the retired
  dependency workflow from being reintroduced.

Maintenance:

- Keep local, CI, and deployment installs locked and update all surfaces
  together when changing dependency workflow.

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

### Resolved since the June review

- #121, "Add a computed temperature to FCU temperature": current code has FCU
  Temp and Room Temp columns, weighted source multipliers, default weights,
  10-minute staleness, popup editing, changelog entries, calculated chart mode,
  set ranges, and rules helpers.
- #35, "`having the graph button display just the graph for that item.`": chart
  device filtering works via `?device_ids=...`, UI links use that path, and the
  chart has Select All / Clear All controls.

- #22, "Migrate the answers of these questions to design documentation.": the
  architecture, local-run, API, schema, and workflow material was moved into
  maintained repository documents.
- #32, #143, and #144: the productized `/map` route and room-administration
  surfaces now exist. Remaining work should use new narrowly scoped issues.

### Keep open

- AI reliability cleanup: #180 through #190.
- Other current work: #177, #170, #156, #152, #142, #129, #127, #118, #117,
  #107, #89, #88, #76, #51, #44, #42, #31, #30, #25, and #1.

These still represent incomplete features, operational gaps, or architectural
work that is visible in the current source.

## Suggested Next Sequence

1. Complete P0 service containment in #180 before installing another checked-in
   unit file.
2. Complete the P1 typed view, transaction, and API contracts in #182, #184,
   and #185.
3. Extract repository/service and bootstrap boundaries through #183 and #187.
4. Split dashboard ownership through #181.
5. Replace the rules engine through #186, ending with supervised shadow and
   production gates.
6. Schedule #188 through #190 according to the secondary milestone dependencies.
