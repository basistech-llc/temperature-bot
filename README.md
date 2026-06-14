# Temperature Bot

Temperature Bot is a Flask application for collecting temperature, HVAC, and
air-quality readings from Hubitat, AE-200, Airthings, AQICN/AirNow, and weather
services. It stores device history in SQLite and serves both web pages and
`/api/v1/*` JSON endpoints.

## Development

Use the Makefile for setup, checks, tests, and local runs.

```bash
make install-macos      # macOS setup
make install-ubuntu     # Ubuntu setup
make make-dev-db        # build a fresh local DB from Flyway migrations
make local-dev          # run Flask locally with simulated AE-200 data
make check              # non-mutating static checks, type checks, and migration validation
make test               # Python and JavaScript tests
```

To run one pytest target through the Makefile:

```bash
make PYTEST_ARGS=tests/test_db.py::test_name pytest
```

## Database

SQLite is the application database for local development and production.
Flyway owns schema migration history under `etc/flyway/sql/`; `etc/schema.sql`
is a generated compatibility schema and should be refreshed with `make schema`
after adding a migration. See `doc/sql-migrations.md`.

Temperatures are stored as integer Celsius tenths (`temp10x`) in `devlog`.
Consecutive readings with the same state are run-length encoded by extending
the row duration instead of inserting duplicate rows.

## Operations

The periodic runner is `bin/runner.py`; production cron/systemd entries run it
against `/var/db/temperature-bot.db`. The `make deploy` target is intended for
the production host only. It pulls code, installs dependencies, validates
Flyway migrations, backs up the production SQLite DB, applies pending
migrations, and validates again.

Tests and local runs use simulator flags for external systems where possible:
`AE200_SIMULATOR=1`, `AIRTHINGS_SIMULATOR=1`, and `AQICN_SIMULATOR=1`.

## References

Hubitat Maker API resources:

- https://hubitat.com/home-automation/maker-api
- https://community.hubitat.com/t/dummies-questions-on-how-to-get-started-with-maker-api/52822
- https://community.hubitat.com/t/consuming-rest-api/100981
- https://community.hubitat.com/t/api-restful-documentation/138586
- https://community.hubitat.com/t/how-to-use-api-to-access-variables/122717
