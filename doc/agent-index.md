# Agent Index

This is a fast navigation index for Codex, Claude, and other code agents. It
does not replace `AGENTS.md`, `CLAUDE.md`, or `.github/copilot-instructions.md`;
read those first for workflow rules, then use this file to find the relevant
surface quickly.

## Workflow Entrypoints

- `doc/hardware-landscape.md`: what the physical equipment is, why only one of
  the Hubitat hubs is reachable, Maker API apps versus dashboards, FCU/ERV
  definitions, and how a device becomes a row. Read this before any hardware
  task if you have not seen the building.
- `doc/site-manual.md`: the census behind that. Which four hubs exist, every
  device on each with its id, the hub-mesh id translation map, the installed
  apps, and exactly which 31 devices Maker API app 520 exposes to us. Use it to
  look up a specific device or id; use it before assuming a device is absent.
- `AGENTS.md`: maintainer workflow selection, signed commit rules, and
  non-interactive shell command requirements.
- `CLAUDE.md`: Claude-specific architecture summary and Makefile test examples.
- `.github/copilot-instructions.md`: broad project map, coding standards,
  Makefile targets, and migration rules.
- `doc/frontend-rendering-strategy.md`: frontend architecture and where SSR,
  JSON APIs, and static JavaScript belong.
- `doc/api-contract.md`: the `/api/v1` error envelope, status/code table,
  response serialization conventions, and which endpoints are deliberately
  still untyped.
- `doc/performance-monitoring.md`: AE-200 request timing, independent network
  probes, storage, charting, deployment, and staging-load experiments.
- `doc/operations-new-instance.md`: instance inventory, new-deployment runbook,
  Flyway-before-first-start ordering, per-instance deploy overrides, and
  rollback.
- `doc/rooms-implementation-review.md`: room dashboard debt, open room issues,
  and Hickory/Kitchen dashboard generalization notes.
- `doc/rooms-implementation-plan.md`: approved FCU-owned room model, grouped
  sensor matrix, room calculations, implementation beads, and issue map.

## Room Dashboard Map

Use this section for `/hickory`, `/kitchen`, `/broadway`, `/room/<room_id>`,
room control tiles, and room dashboard frontend work.

- `app/routes_web.py`
  - `_render_room_dashboard_with_data()`: gathers room dashboard data and
    renders `room_dashboard.html`.
  - `_find_room()`: resolves a room key by room name, then by owning FCU name.
  - `_member_room_ids()`: resolves a dashboard's member rooms and warns about
    keys that match nothing.
  - `_canonical_room_sensors()`: sensor tiles for a set of room ids.
- `app/room_config.py`
  - Per-dashboard member rooms, AE-200 unit names, and actuator controls.
    Sensor membership is canonical and is never listed here.
  - Broadway spans four rooms and configures nine switches plus a fan; its
    devices live on the Hubitat hub we cannot reach.
- `app/models.py`
  - `RoomConfig`, `RoomControl`, `RoomControlKind`: the control vocabulary.
    Adding a control is a config entry, not new markup or a new endpoint.
- `app/templates/room_dashboard.html`
  - Shared room dashboard Jinja template. Loops the configured control list and
    pre-renders HVAC cards, sensors, live clock, and script includes.
- `app/static/room_dashboard.js`
  - Room dashboard behavior: speed buttons, set temperature controls, configured
    room controls, polling, and scale-to-fit.
  - `applyControlState()`: applies one polled control state to its tile.
  - Derives room-control endpoints from the template's room key, and addresses
    controls by `data-control-key`.
- `app/routes_api.py`
  - `/api/v1/status`: live HVAC/device status.
  - `/api/v1/set_drive`, `/api/v1/set_fan_speed`, `/api/v1/set_temp`: HVAC
    control APIs.
  - `/api/v1/room/<room_key>/room_status`, `/switch`, `/dimmer`, `/fan`, `/tv`:
    configured room-control APIs. `/wall_light` and the Hickory aliases remain
    compatible, each under its own Flask endpoint name.

## Canonical Room Metrics

- `app/room_metrics.py`
  - Typed room membership, device eligibility, metric extraction, and shared
    10-minute freshness selection for temperature and humidity.
- `app/db.py`
  - `fetch_latest_room_metric_snapshots()`: raw SQLite latest-reading lookup
    that feeds the room metric selector without Flask request state.
- `tests/test_room_metrics.py`
  - SQLite-backed coverage of membership, staleness, exclusions, missing
    values, and Hubitat/Airthings payload shapes.
- `app/static/room_matrix.js`
  - Air Quality matrix drag assignment, sorted placement, optimistic rollback,
    room creation/rename/deletion, and live room summary updates.
  - The Air Quality matrix is the main-page room administration surface. FCU
    unit names remain separate from their FCU-owned room names.
- `tests/test_room_matrix_routes.py` and `tests/test_room_matrix.js`
  - SQLite-backed grouping/rendering contracts and substantive client state
    transitions.

## Alert Rules

- `doc/alerts.md`
  - Monitoring/action rule separation, Airthings stuck detection, reminder
    cadence, persistence, and Slack delivery.
- `bin/rules.py`
  - Defines both `run_rules_for_device()` and
    `run_alert_rules_for_device()`.
- `app/rules_engine.py` and `app/db_alerts.py`
  - Evaluate alert conditions independently of the HVAC master switch and
    persist notification events before delivery.

## Hickory Life Easter Egg

Recommended implementation shape:

- Add `app/static/hickory_life.js`.
- Load it only when `location == 'Hickory'` from `room_dashboard.html`.
- Keep Hickory-only hidden gestures in this same module; it also owns the
  repeated same-corner reload gesture.
- Keep it self-contained:
  - attach its own `DOMContentLoaded` listener;
  - add four-corner `pointerdown` sequence detection;
  - add repeated same-corner press detection for the reload gesture;
  - inject its own overlay, dialog, canvas, and style element;
  - exit cleanly and remove DOM/timers on click;
  - export only pure helper functions for Node tests.
- Do not modify `room_dashboard.js` unless the implementation proves it needs a
  shared hook. The easter egg should not interfere with HVAC polling, control
  buttons, or scale-to-fit.

Corner trigger guidance:

- Use viewport-relative hit zones, not existing button coordinates.
- Require the sequence top-left, top-right, bottom-left, bottom-right.
- Keep a short timeout between taps so normal dashboard touches do not unlock
  the dialog accidentally.
- Be careful with top-right: the room dashboard temperature toggle is also near
  that corner.
- The reload gesture is separate from the Life sequence: four presses in the
  same corner within four seconds flash "reloading" for 0.25 seconds, then
  reload the page.

Game of Life guidance:

- A local implementation is probably simpler than adding an npm dependency.
- Use a finite grid sized from the canvas; wrapping is optional but should be
  explicit.
- Run at 5 generations per second.
- Track recent board hashes to reset on:
  - empty board;
  - unchanged stable board;
  - a repeated board within a small window, such as blinkers or other cycles.
- Stop the animation and restore the dashboard on any click/tap while Life is
  running.

Dialog guidance:

- Pick the Deuteronomy 30:19 translation deliberately. KJV is public domain in
  the United States; many modern translations are copyrighted.
- Render the quote in a font stack that degrades cleanly if no blackletter font
  is installed.
- "Choose life" starts the Life overlay.
- "Do not choose life" shows a skull-and-crossbones state briefly, then returns
  to the normal Hickory dashboard.

Useful existing package references if a dependency is preferred:

- `@rankdim/conway`: small MIT browser/canvas package with UMD build and
  patterns including glider gun.
- `games-of-life`: MIT, no dependencies, abstract functional Life engine; less
  directly useful for a canvas popup.

## Tests And Checks

Run checks through the Makefile.

- JavaScript unit tests: `make test-js`
- ESLint: `make eslint`
- Template lint: `make djlint`
- Broader non-mutating checks: `make check`

For the Hickory Life easter egg, useful substantive tests would cover:

- a block remains stable;
- a blinker repeats after two generations;
- a lonely cell dies;
- empty and repeated boards are detected as reset conditions;
- the four-corner recognizer accepts only the intended sequence and timeout.

Place focused Node tests under `tests/test_hickory_life.js` and add that file
to the `test-js` target in `Makefile`.
