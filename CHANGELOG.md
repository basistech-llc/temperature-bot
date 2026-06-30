# Changelog

> Versions 0.0.0–0.0.57 are reconstructed retroactively from git history (back
> to the initial commit) and were never assigned version numbers at the time;
> the numbering is synthetic. Add changes under `## Unreleased`; `make release`
> (or `release-minor` / `release-major`) stamps them into a dated release and
> tags it.

## Unreleased

* [feature] Formal version system: a top-level `VERSION` file is the single
  source of truth, surfaced as `v<version> (git sha: <sha>)` in the About-page
  footer and the `/version` page, plus a `sha` field on `/api/v1/version`.
* [feature] This CHANGELOG and `make release` / `release-minor` / `release-major`
  targets (via `bin/release.py`) that bump the version, stamp the changelog, and
  create a `vX.Y.Z` git tag.

## v0.0.57 (30Jun26)

* [feature] Self-documenting `make help` with a one-line description on every target.
* [cleanup] Renamed the Deep Dive labels and synced the About page to match.

## v0.0.56 (29Jun26)

* [cleanup] Carl UI review: decluttered and reordered the room dashboard, fit the per-room HVAC page to the viewport with a scale-to-fit safety, and restored the Beads instructions conditionally per the active developer.

## v0.0.55 (23Jun26)

* [feature] Hubitat simulator for local development and tests.
* [feature] AE-200 dry and auto mode support.
* [feature] Per-device metadata controls (display name, type, rules enablement, notes).
* [bug-fix] Rules dry-run edge cases and inconsistent logging in the rules engine.
* [bug-fix] General test cleanup and a runner bug fix; tech-debt cleanup.
* [cleanup] Modernized the rules-engine execution path and rewrote the rules engine.

## v0.0.54 (17Jun26)

* [feature] FCU mode control.
* [bug-fix] Legacy Airthings chart timestamps.
* [cleanup] Hardened AE-200 live controls and the simulator UI.
* [cleanup] Made temperature-source edits save atomically.
* [cleanup] Updated air-quality matrix coloring.

## v0.0.53 (15Jun26)

* [feature] Persisted FCU temperature ranges.
* [bug-fix] Per-device chart data fetches.
* [cleanup] Screenshot infrastructure: inline PR screenshots, stopped publishing screenshot branches, removed Imgur usage.
* [cleanup] Removed a stale DynamoDB reference.

## v0.0.52 (14Jun26)

* [feature] Calculated (derived) temperature: backend, UI, schema guard, and acceptance tests.
* [feature] FCU mode column on the main grid.
* [feature] Initial web-UI screenshot workflow for pull requests.
* [cleanup] Clarified legacy `.beads` guidance in the agent docs.

## v0.0.51 (13Jun26)

* [feature] Pydantic model contracts in place of dict-shaped data passed through the app.
* [bug-fix] Weather error payloads are now preserved.
* [bug-fix] CI type, ESLint, and djlint checks.
* [cleanup] Hardened the docs and data-contract standards; banned blanket type-ignores.

## v0.0.50 (10Jun26)

* [feature] Flyway database migrations, wired into `make-dev-db`, `migrate-db`, `schema`, and the deploy targets, with a baseline schema.
* [bug-fix] CI Flyway install, PATH, and download-URL issues.
* [bug-fix] "Disable for" column header now reads "Disabled for".
* [cleanup] Hardened the Flyway schema dump.

## v0.0.49 (04Jun26)

* [feature] Added no-return Rooms menu items for Kitchen and Hickory.
* [bug-fix] FCU "Off" reverting to "Auto" on the main grid.
* [cleanup] Widened room control buttons to fill the full row.
* [cleanup] Removed the italicized secondary room name from sensor tiles.

## v0.0.48 (31May26)

* [bug-fix] Auto button staying highlighted when a unit is off.
* [bug-fix] Kept the "was …" speed accurate during fast transitions.
* [bug-fix] Speed buttons no longer disable during in-flight requests.
* [bug-fix] Removed a duplicate `temperature_utils.js` include on the room dashboard.
* [cleanup] Replaced raw "Speed N" fan labels with friendly, context-aware UX.
* [cleanup] Room dashboard now updates optimistically on speed/drive change.
* [cleanup] Removed the Area 51 fan from the Hickory room page.
* [cleanup] Updated most dependencies.

## v0.0.47 (21Apr26)

* [feature] Click-to-chart for Air Quality columns on the home and `/air-quality` pages.
* [feature] "Disable for" column with ± controls and a Resume Rules column on the home page.
* [feature] Tests for AQ metric helpers and `/metric` endpoints.

## v0.0.46 (19Apr26)

* [feature] Set-temperature controls on room dashboards, showing all FCUs.
* [feature] Unit tests for speed-control device filtering.
* [cleanup] Restyled the alerts page and remaining pages to match site conventions.
* [cleanup] Updated dependencies.
* [cleanup] Removed dead CSS.

## v0.0.45 (13Apr26)

* [feature] Hickory room API endpoints with tests.
* [feature] Weather module tests (CI coverage 17% → 94%).
* [cleanup] Redesigned the weather page to match site conventions.
* [cleanup] Equalized data-table widths with CSS Grid and tightened column padding.
* [cleanup] Pale-green background on the FCU Auto fan-speed column.
* [cleanup] Full date labels on the air-quality chart x-axis.
* [cleanup] Conditional room-dashboard back button via an embedded query param.

## v0.0.44 (09Apr26)

* [feature] Hickory room dashboard: wall light controls (tile grid), a light dimmer, a TV position control, a live minute-aligned clock, and a humidity sensor.
* [bug-fix] Hubitat offline handling; corrected the Cage Sensor name.
* [cleanup] Compacted the room dashboard layout for smaller screens.
* [cleanup] Removed the Area 51 sensors.

## v0.0.43 (31Mar26)

* [feature] Command to raise and lower the TV.
* [feature] Tooling to centralize and check Jinja dependency versions.
* [cleanup] Updated Python and JavaScript dependencies; `make outdated` now rebuilds and catches JS dependencies too.
* [cleanup] Removed unused tooling.

## v0.0.42 (25Mar26)

* [feature] Stale-data indicators on all data columns of the main and air-quality pages.
* [feature] Radon shown in pCi/L when Fahrenheit (US units) is selected.
* [feature] Beads issue tracking.
* [cleanup] Unified table styling with a shared `data-table` class, moving units into headers.
* [cleanup] Replaced chart lozenge buttons with clickable data cells; widened Notes columns.
* [cleanup] Highlight parent menu items when a submenu page is active.
* [cleanup] Pinned all dependency versions.

## v0.0.41 (23Mar26)

* [feature] Airthings air-quality columns on the main-page Air Quality table.
* [feature] Database backup targets and indexes.
* [bug-fix] Lighting chart now shows all illuminance sensors.
* [cleanup] Improved main-page chart navigation and badge UX; highlighted the AQI line in the air-quality chart.

## v0.0.40 (15Mar26)

* [cleanup] Renamed the Admin menu item to Deep Dive.
* [cleanup] Air-quality table presentation with C/F support.
* [cleanup] Temperature chart draws one line per sensor when display names duplicate.

## v0.0.39 (11Mar26)

* [bug-fix] Rules runner spamming "disabled timer expired" logs.
* [cleanup] Split the temperature chart into separate temperature and lighting charts, excluding lights and dimmers from the temperature view.
* [cleanup] Improved Today's Log formatting.
* [cleanup] Show the full name in chart hover text to distinguish duplicate names.

## v0.0.38 (10Mar26)

* [feature] Global rules kill switch in the header.

## v0.0.37 (09Mar26)

* [feature] Humidity and illuminance collected from Hubitat; humidity for Airthings.
* [cleanup] Centralized human-friendly device naming, eliding the " on XXX" suffix.
* [cleanup] Made temperature-adjustment widgets easier to use on touch displays.

## v0.0.36 (05Mar26)

* [feature] Indoor air-quality (AQI) page with a header and a formatted indoor AQI table.
* [cleanup] AQI timestamps now come from the database rather than the last polling time.
* [cleanup] Cleaner displayed device names.
* [cleanup] Documented the frontend rendering strategy in an LLM-friendly format.

## v0.0.35 (24Feb26)

* [feature] New rooms on the dev map.
* [bug-fix] `etc/schema.sql` target prerequisites.
* [cleanup] Makefile DEV_DB creation with error handling; configurable `fetch-dev-db`.

## v0.0.34 (22Feb26)

* [feature] Air-quality page (`/air-quality`) with smoke tests.
* [feature] Floorplan plus an HTML/JS tool for computing bounding boxes.
* [feature] Rules documentation.
* [cleanup] Removed all inline styles; fixed air-quality table semantics.
* [cleanup] Hardened against SQL injection.

## v0.0.33 (17Feb26)

* [feature] Airthings air-quality integration (radon, CO2, VOC) with a simulator.

## v0.0.32 (29Jan26)

* [feature] Separate pages for temperature and air-quality charts.
* [feature] Tests for sensor selection.
* [bug-fix] Test error from a missing coroutine handler; pylint issues.
* [cleanup] Show the device label rather than the internal name for Hubitat devices.
* [cleanup] Refactored to reduce module size; moved some tests out of Playwright.

## v0.0.31 (28Jan26)

* [feature] Temperature setting for FCUs and display of set temperatures.
* [cleanup] Adjusted main-page labels for better fit.
* [cleanup] Copyright footer shown only on the About page.

## v0.0.30 (27Jan26)

* [cleanup] Split ERV and FCU units into separate sections.
* [cleanup] Moved the weather section to a dedicated Weather tab.

## v0.0.29 (05Jan26)

* [feature] About-page information.
* [bug-fix] Lag updating between Fahrenheit and Celsius, including the weather section.
* [cleanup] Renamed the main menu item to "BasisTech HVAC".
* [cleanup] Moved Charts, Alerts, Rules, and Today's Log under a new Admin menu.
* [cleanup] Promoted `/dbg/all_devices` to a first-class Admin page.
* [cleanup] Friendlier fan-speed controls; only show temperature for devices that have it.

## v0.0.28 (24Dec25)

* [cleanup] Renamed Studio to Hickory.
* [cleanup] Replaced the Buttons page with a Rooms dropdown.
* [cleanup] Replaced the Motor toggle with an Off button on room pages.
* [cleanup] Combined minor pages.

## v0.0.27 (15Dec25)

* [feature] AE-200 data on the debug page.
* [cleanup] Avoid rerunning schema setup when the DB schema is unchanged.
* [cleanup] Documented local dev DB cloning and live-dev-web usage.

## v0.0.26 (30Nov25)

* [feature] First room (tablet) pages for Kitchen and Studio.
* [feature] `/dbg/all_devices` endpoint.
* [feature] Editable notes.
* [bug-fix] Fan/ERV buttons now better match device characteristics.
* [cleanup] Nicer temperature-sensor layout on room pages.
* [cleanup] Retired the old Buttons page into links to the new pages.

## v0.0.25 (03Nov25)

* [feature] JavaScript testing.
* [feature] Days shown in duration strings.
* [bug-fix] Status details for all alerts, including long-running ones.

## v0.0.24 (28Oct25)

* [feature] Tests for the alerting code.
* [feature] Device status (temperature, speed) shown on each alert row.
* [cleanup] Times shown with timezone in 24-hour format.
* [cleanup] Sensors sorted alphabetically.
* [cleanup] Added Copilot repository instructions.

## v0.0.23 (27Oct25)

* [bug-fix] Both tables showing when entering the Alerts tab.
* [bug-fix] Installation on GitHub Linux CI.
* [cleanup] Colorized alert tables and removed the extraneous Status column.
* [cleanup] Show device names instead of internal IDs in dropdowns.
* [cleanup] Widened alert columns to fit dates.

## v0.0.22 (24Oct25)

* [feature] Basic alerting.

## v0.0.21 (22Oct25)

* [feature] C/F toggle for all temperatures.
* [feature] Select/unselect-all sensor buttons and an "all" range button for charts.
* [feature] GitHub menu popup with repo and bug-report links.
* [feature] `make deploy`.
* [cleanup] Show all sensors (disabling unused ones) to avoid page jumpiness.
* [cleanup] Highlight the selected menu item and date-range button.
* [cleanup] Case-insensitive sensor sorting.

## v0.0.20 (20Oct25)

* [feature] systemd service configs for the deg1 and slg1 deployments.

## v0.0.19 (14Oct25)

* [feature] AQI charts.
* [bug-fix] Chart rendering and a rules error.

## v0.0.18 (11Oct25)

* [feature] Rule disabling for a period after a manual change, with validation.
* [feature] Pruning of expired rules.
* [feature] `?only=` filter for the Buttons page.
* [cleanup] Cleaned up AI-generated code (the `routes/` directory, redundant tests, and stray services).

## v0.0.17 (08Oct25)

* [bug-fix] Stabilized the test suite (memory allocation, `temp_db` fixture) and cleaned up linting.

## v0.0.16 (30Sep25)

* [feature] "Disabled until" indicator on the index page.
* [cleanup] AQI capture and an updated schema.

## v0.0.15 (27Sep25)

* [feature] AQICN integration (token and handling).
* [feature] Initial simulator.
* [feature] Pre-commit hooks and codecov coverage.
* [cleanup] Cleaner YAML handling for test cases; general refactoring.

## v0.0.14 (20Sep25)

* [feature] Airthings integration (first working version).
* [feature] Modbus support.
* [feature] AQICN handling.
* [cleanup] Rules keep the restroom at speed 4.

## v0.0.13 (31Aug25)

* [bug-fix] Chart page rendering.
* [cleanup] New rules; updated the Buttons UI.

## v0.0.12 (09Aug25)

* [feature] Hubitat AppId.
* [cleanup] Split fan control into individual drive and speed (was a combined `fan_drive_speed`).
* [cleanup] Broke the device display into two tables.

## v0.0.11 (03Aug25)

* [bug-fix] Handling of unknown or missing secrets.
* [cleanup] Rules now use the stored AQI; tuned AQI thresholds and fan speeds.

## v0.0.10 (29Jul25)

* [feature] Rules engine with a rule-disable feature.
* [feature] AQI stored in the database.
* [cleanup] Renamed lat/lon to latitude/longitude.

## v0.0.9 (17Jul25)

* [feature] Time-series charts and a device dropdown on the chart page.
* [bug-fix] Async handler event-loop conflict; speed-control display.
* [cleanup] Moved table creation from JavaScript to Jinja2; added styling.

## v0.0.8 (12Jul25)

* [feature] JavaScript/UX testing and ESLint.
* [cleanup] Migrated the web app from FastAPI to Flask.
* [cleanup] Display rule-execution results; moved the changelog into the rules engine.

## v0.0.7 (10Jul25)

* [feature] Weather support, splitting `/status` into `/status` and `/weather`.
* [feature] AirNow tests.
* [bug-fix] Error handling in AE-200, AirNow, and weather.
* [cleanup] Migrated to Poetry.

## v0.0.6 (06Jul25)

* [cleanup] Renamed the `myapp` package to `app`.
* [cleanup] Status is now generated for all devices.

## v0.0.5 (03Jul25)

* [feature] SQLite logging of Hubitat and AE-200 readings, extending existing rows or recording new values.
* [feature] Weekly and monthly cleanup; periodic averages.
* [cleanup] Device-logging schema.

## v0.0.4 (30Jun25)

* [feature] codecov support.
* [feature] Display of all fan speeds.
* [cleanup] Switched dependency install to uv.
* [cleanup] Skip certain tests on GitHub CI.

## v0.0.3 (27Jun25)

* [feature] AQI capture, logging, and tests.
* [cleanup] Migrated to a SQLite database backend; favicon display.

## v0.0.2 (23Jun25)

* [cleanup] ERV speed controls now use radio buttons; nicer CSS styling.

## v0.0.1 (12Jun25)

* [feature] Initial application implementation with updates and AQI.

## v0.0.0 (08Jan25)

* [feature] Initial commit and a working data uploader.
