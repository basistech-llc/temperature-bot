# Temperature Bot

Temperature Bot is a Flask application for collecting temperature, HVAC, and
air-quality readings from Hubitat, AE-200, Airthings, AQICN/AirNow, and weather
services. It stores device history in SQLite and serves both web pages and
`/api/v1/*` JSON endpoints.

## Development

Use the Makefile for setup, checks, tests, and local runs.
Python dependencies and the in-project `.venv` are managed by uv from the
committed `uv.lock` file.

```bash
make install-macos      # macOS setup
make install-ubuntu     # Ubuntu setup
make make-dev-db        # build a fresh local DB from Flyway migrations
make local-dev          # run Flask locally with simulated AE-200 data and banner
make local-live-dev     # run Flask locally against live AE-200 hardware
make check              # non-mutating static checks, type checks, and migration validation
make test               # Python and JavaScript tests
make web-screenshots    # render each web UI page to PNG screenshots
```

To run one pytest target through the Makefile:

```bash
make PYTEST_ARGS=tests/test_db.py::test_name pytest
```

`make web-screenshots` seeds a temporary SQLite database, starts Flask with
simulated external services, and writes PNGs plus `manifest.json` and
`gallery.md` under `var/web-ui-screenshots/`. The Ubuntu-only `Web UI
Screenshots` pull-request workflow uploads those PNGs as GitHub release assets
and updates a sticky PR comment with inline rendered images.

## Database

SQLite is the application database for local development and production.
Flyway owns schema migration history under `etc/flyway/sql/`; `etc/schema.sql`
is a generated compatibility schema and should be refreshed with `make schema`
after adding a migration. See `doc/sql-migrations.md`.

Temperatures are stored as integer Celsius tenths (`temp10x`) in `devlog`.
Consecutive readings with the same state are run-length encoded by extending
the row duration instead of inserting duplicate rows.

FCUs can also report a calculated room temperature: a weighted average of the
FCU's own raw temperature and configured temperature-reporting devices. Room
metadata, map polygons, source multipliers, persisted FCU set ranges, API
payloads, and rule semantics are documented in
`doc/calculated-temperatures-and-rooms.md`.

AE-200 control currently stays inside the Flask app behind a serialized async
bridge. The tradeoffs for a future FastAPI/async/websocket migration are in
`doc/fastapi-async-ae200.md`.

## Data Contracts

Stable app-owned data should use Pydantic models from `app/models.py` rather
than ad hoc dictionaries. Named models document the expected fields, make type
and runtime validation useful, and give humans and LLM coding agents a clearer
source of truth. External service payloads may remain dictionaries at the
edge, but shared keys should be centralized instead of repeated inline.

## Operations

The periodic runner is `bin/runner.py`; canonical production scheduling is now
defined by checked-in systemd oneshot services and timers that run it against
`/var/db/temperature_bot/temperature-bot.db`. See
`doc/systemd-scheduled-jobs.md` for installation, observation, and deployment
quiescence. The units are not installed by this repository change. The `make
deploy` target is intended for the production host only. It pulls code, installs
dependencies, validates Flyway migrations, backs up the production SQLite DB,
applies pending migrations, and validates again.

`doc/DEPLOYMENT_PACKAGE.md` defines the ZIP artifact containing the wheel,
locked runtime requirements, Flyway migrations, systemd units, installer, and
manifest. Pull requests build and install this package in a disposable root;
their Actions artifacts expire after five days and are not production releases.

To stand up a new instance, or an additional observation instance on the shared
server, follow `doc/operations-new-instance.md`.

Tests and local runs use simulator flags for external systems where possible:
`AE200_SIMULATOR=1`, `AIRTHINGS_SIMULATOR=1`, and `AQICN_SIMULATOR=1`.

## References

Hubitat Maker API resources:

- Temperature Bot Hubitat integration notes: `doc/Hubitat_Info.md`
- https://hubitat.com/home-automation/maker-api
- https://community.hubitat.com/t/dummies-questions-on-how-to-get-started-with-maker-api/52822
- https://community.hubitat.com/t/consuming-rest-api/100981
- https://community.hubitat.com/t/api-restful-documentation/138586
- https://community.hubitat.com/t/how-to-use-api-to-access-variables/122717
