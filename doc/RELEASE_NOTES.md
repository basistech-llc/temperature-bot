# Temperature Bot release notes

This changelog summarizes meaningful changes on the main development line. It
was reconstructed from the complete Git history through 2026-08-26; merge,
format-only, checkpoint, and follow-up fix commits are consolidated into the
change they completed.

## Unreleased

### Deployment and operations

- Migrated dependency management and CI from Poetry to `uv`, with pinned setup
  tooling and macOS setup support.
- Changed production services to use the dedicated service-account database
  path and documented the live database inventory and ownership model.
- Added deployable, checksummed application packages, an installer and verifier,
  systemd scheduled-service/timer units, and CI coverage for package assembly.
- Made SQLite backups transactionally safe, restricted snapshot permissions,
  and corrected installed service paths.
- Reworked `make fetch-dev-db` to preserve the previous local database
  directory, stream a non-privileged read-only SQLite dump into
  `var/db/temperature_bot`, apply Flyway migrations, and report each operation.

## 0.11.0 - 2026-08-20

### Room dashboards and hardware

- Added the Broadway dashboard and generalized configured room controls beyond
  Hickory and Kitchen.
- Corrected Broadway device mappings, accepted both known Maker API response
  shapes, and kept unavailable controls visible without inventing device state.
- Activated the Broadway TV Cart controls and strengthened the test guard that
  prevents tests from contacting real Hubitat hardware.
- Improved room control tiles, sensor-silence reporting, and per-device status
  handling.
- Added a surveyed hardware landscape and a complete four-hub site manual; the
  Word manual is now generated from the Markdown source.

### Reliability, APIs, and operations

- Reduced dashboard polling load, indexed latest-reading queries, refreshed
  status immediately on load, prevented overlapping requests, and preserved the
  latest FCU selection and sensor icons.
- Isolated staging deployments, removed Gunicorn reloaders from service units,
  and required explicit true values for simulator flags.
- Added durable alert delivery, Airthings stuck-sensor and AE-200 alerts,
  reminder scheduling, unique active-alert enforcement, stale-input rejection,
  and per-device failure isolation.
- Added AE-200 performance monitoring, network probes, controller notifications,
  diagnostics, protocol-error classification, bounded acknowledgements, and
  atomic FCU writes.
- Added CSV downloads to metric, lighting, AQI, and FCU charts.
- Standardized `/api/v1` on a typed error envelope, Pydantic request models,
  typed domain errors, and strict dashboard view models.
- Added the new-instance operations runbook and codified the multi-developer
  branch, pull-request, and Beads workflow.

## 0.10.0 - 2026-07-13

### Canonical rooms

- Introduced FCU-owned canonical rooms, typed room assignment APIs, room
  membership and presence history, and database schema preflight checks.
- Rebuilt the air-quality sensor matrix around room membership, including room
  creation, rename, deletion, drag assignment, and live summaries.
- Applied canonical rooms to FCU metrics, combined history charts, the HVAC
  map, and configured room dashboards.
- Separated room names from FCU unit names and hardened deletion, rename,
  polling, status, and icon refresh behavior.

### Charts and controls

- Added temperature-chart navigation and zoom, calculated-temperature
  explanations, accurate gaps for missing data, and optimized boundary queries.
- Disabled FCU set-temperature controls in Dry mode and refined FCU setpoint
  controls.
- Added inferred device types and an FCU humidity placeholder column.

## 0.9.1 - 2026-07-11

### Controls, charts, and diagnostics

- Refined FCU room editing, setpoint range semantics, control feedback, and
  status behavior.
- Added accurate chart gaps for missing temperature data and deployment version,
  branch, and commit metadata in the footer and version endpoints.
- Added the Hickory “Choose Life” easter egg and the four-corner reload gesture.

## 0.1.0 development history

The project used version `0.1.0` from its initial packaging through 2026-07-10.
The dated sections below preserve the major changes made during that period.

### 2026-06

- Adopted Flyway migrations, baseline and schema validation, deployment-time
  migration, and schema-dump hardening.
- Replaced dictionary-shaped internal contracts with Pydantic models and
  strengthened documentation, lint, type, template, and screenshot CI checks.
- Added calculated temperatures with editable weighted sources, atomic saves,
  chart support, and schema guards.
- Added persisted FCU setpoint ranges, FCU mode controls including Dry and Auto,
  and safer AE-200 live controls.
- Modernized the rules engine, added device metadata editing, completed the
  Hubitat simulator, and added Slack rule notifications.
- Improved dashboard freshness handling and made room dashboards responsive to
  small touch displays.
- Added technical-debt and operational documentation and clarified the project’s
  GitHub-versus-Beads workflow.

### 2026-05

- Improved room-dashboard fan labels and optimistic control feedback while
  preserving accurate state during rapid transitions.
- Fixed incorrect Auto highlighting, duplicate scripts, and the obsolete Area
  51 fan control.
- Updated pinned dependencies.

### 2026-04

- Expanded the Hickory dashboard with humidity, clock, TV position, dimmer,
  wall-light, and set-temperature controls, plus offline-sensor handling and a
  compact tile layout.
- Restyled Weather, Alerts, and remaining pages to use shared site conventions.
- Added full chart date labels, click-to-chart behavior for air-quality metrics,
  FCU Auto highlighting, and home-page rule-disable/resume controls.
- Added tests for room APIs, weather behavior, AQ metric edge cases, and room
  filtering.

### 2026-03

- Reworked the Air Quality page with database timestamps, clearer device names,
  improved tables, and Fahrenheit support.
- Collected and displayed additional Hubitat and Airthings humidity and
  illuminance data.
- Split temperature and lighting charts, improved duplicate-sensor handling,
  chart navigation, stale-data indicators, and US radon units.
- Added a global rules kill switch and fixed repeated “disabled timer expired”
  log messages.
- Unified table styling, improved touch controls, and added the first Hickory TV
  command.
- Added database indexes and backup targets, pinned dependencies, dependency
  auditing, and removed unused tooling.

### 2026-02

- Added Airthings collection and simulator support.
- Added the indoor Air Quality page, floor plan, room data, schema updates, and
  tools for defining floor-plan bounding boxes.
- Hardened SQL construction and improved the development-database and schema
  Make targets.
- Added rules documentation, frontend rendering guidance, semantic HTML fixes,
  and route smoke tests.

### 2026-01

- Reorganized navigation around BasisTech HVAC, Admin, Weather, separate ERV
  and FCU sections, and first-class device diagnostics.
- Added FCU set-temperature controls and displayed setpoints.
- Split temperature and air-quality chart pages and improved sensor selection.
- Improved the C/F control, fan-speed controls, stale/missing temperature
  presentation, naming, About information, and test coverage.

### 2025-12

- Added Kitchen and Hickory room pages, renamed Studio to Hickory, replaced the
  old Buttons page with a Rooms menu, and improved room sensor and Off controls.
- Added editable notes and clearer rule-disabled notices.
- Added AE-200 information to the device diagnostics page.
- Avoided unnecessary schema setup when the schema had not changed and
  documented local development database cloning.

### 2025-11

- Improved long-duration and detailed alert status display and began JavaScript
  unit testing.
- Added Kitchen and Studio routes and the all-devices diagnostics endpoint.
- Added the first working room pages and retired the old Buttons page in favor
  of room links.
- Corrected Fan and ERV controls to match device capabilities.

### 2025-10-23 through 2025-10-31

- Added alert creation and display, device-name filtering, severity styling,
  device status details, timezone-aware 24-hour timestamps, and substantive
  alert tests.
- Added `make live-dev-web` and `make live-dev-runner` and repaired Linux and
  macOS installation paths.
- Made chart sensor sorting case-insensitive.

### 2025-10-22

- Added `make deploy`.
- Added bulk select/unselect and an `all` button for sensor charts.
- Kept inactive sensors visible but disabled to prevent layout jumps.
- Highlighted selected date ranges and menu items and distinguished selection
  controls from action buttons.

### 2025-10-21

- Added a Celsius/Fahrenheit switch across displayed temperatures.
- Improved margins and new-machine startup tooling.
- Added `make clean` and `make cleanall` and reliable database initialization.

### 2025-10-01 through 2025-10-20

- Made device control changes disable rules for that device for three hours and
  prune expired disable periods.
- Allowed air-quality variables in rules and repaired the AQI charts.
- Added GitHub repository and bug-report links to the UI.
- Added development and production service configurations and deployment notes.
- Added optional chart device selection through the `dropdown` query parameter.

### 2025-09

- Added Modbus and Airthings integrations and AQICN support.
- Added the Hubitat simulator, safer secret and YAML handling, and pre-commit,
  CI, browser, lint, and coverage improvements.
- Restored clogging/AQI data handling and updated the database schema.

### 2025-08

- Split combined fan drive/speed state into separate controls and tables and
  added Hubitat Maker API application identifiers.
- Revised HVAC and AQI rules, button behavior, and charts.
- Improved handling of missing secrets and stored AQI values.

### 2025-07

- Built the SQLite logging pipeline for Hubitat and AE-200 readings, schema
  extension, aggregates, and weekly/monthly cleanup.
- Added weather and outdoor AQI ingestion, storage, and error handling.
- Migrated the web application from FastAPI to Flask and added status, weather,
  chart, device-selection, rule-result, and speed-control interfaces.
- Added the rules engine and temporary rule disabling.
- Established Python, JavaScript, browser, lint, and CI test workflows and
  initially adopted Poetry for dependency management.

### 2025-06

- Implemented the initial HVAC and AQI application, AE-200 controls, ERV speed
  radio buttons, logging, and the SQLite database.
- Added tests, Codecov reporting, and early `uv`-based setup work.

### 2025-01

- Created the repository and its initial uploader.
