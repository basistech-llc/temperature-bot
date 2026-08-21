# Copilot Instructions for Temperature Bot

## Project Overview

Temperature Bot is a Flask application for monitoring and controlling HVAC,
temperature, lighting, and air-quality devices. It collects data from Hubitat,
AE-200, Airthings, AQICN/AirNow, and weather services; stores history in
SQLite; and exposes server-rendered pages plus `/api/v1/*` JSON endpoints.

## Technology Stack

- Python 3.12+
- Flask and Jinja2
- SQLite for local development and production
- Flyway for SQL schema migrations
- uv 0.11.26 for Python dependency management
- Ruff, Pylint, djlint, ESLint, mypy, pytest, and Playwright

## Project Structure

```text
temperature-bot/
├── app/
│   ├── main.py                         # Flask app factory and error handling
│   ├── routes_api.py                   # REST API endpoints (/api/v1)
│   ├── routes_web.py                   # Web UI routes
│   ├── db.py                           # SQLite access layer
│   ├── models.py                       # Pydantic request/response contracts
│   ├── rules_engine.py                 # HVAC control rules
│   ├── hubitat.py                      # Hubitat integration
│   ├── ae200.py                        # AE-200 HVAC controller integration
│   ├── airquality.py                   # Outdoor air-quality integration
│   ├── weather.py                      # National Weather Service integration
│   ├── templates/                      # Jinja templates
│   ├── static/                         # JavaScript, CSS, images
│   └── utils/                          # Shared helpers
├── bin/
│   ├── runner.py                       # Periodic data collection runner
│   ├── rules.py                        # Rules management CLI
│   └── fix.py                          # Maintenance helper
├── etc/
│   ├── flyway/sql/                     # Canonical Flyway migrations
│   ├── schema.sql                      # Generated compatibility schema
│   └── *.service                       # systemd units
├── tests/
│   ├── conftest.py                     # Pytest fixtures
│   ├── helpers/                        # Test helpers
│   └── test_*.py
└── lib/ctools                          # External submodule, excluded from linting
```

## Required Workflow

Use the Makefile for setup, checks, tests, and local runs. Do not bypass it
with direct `uv run pytest` or ad hoc command sequences unless you are
debugging a Makefile target itself.

```bash
make install-macos
make install-ubuntu
make make-dev-db
make local-dev
make check
make test
```

To run one pytest target:

```bash
make PYTEST_ARGS=tests/test_db.py::test_function_name pytest
```

## Database and Migrations

- Flyway migrations under `etc/flyway/sql/` are canonical.
- `etc/schema.sql` is generated from Flyway migrations with `make schema`.
- Do not hand-edit `etc/schema.sql` for schema changes.
- Validate migrations with `make validate-migrations`.
- Apply local pending migrations with `make migrate-db`.
- Production deploy is `make deploy` on the production host. It validates
  Flyway state, backs up `/var/db/temperature-bot.db`, migrates, and validates
  again.

When adding schema:

1. Add the next versioned migration, for example `V3__add_alert_indexes.sql`.
2. Run `make schema`.
3. Run `make validate-migrations`.
4. Add substantive tests for behavior that depends on the schema change.

## Coding Standards

- Be precise and keep code compact.
- Keep documentation consistent with actual behavior.
- Prefer Pydantic models for structured data.
- Avoid dictionaries as internal structures. When an external API forces a
  dictionary shape, define key names once as string constants instead of
  hard-coding them at each use.
- Keep route handlers thin; move business logic into focused modules.
- Do not add `type: ignore` comments. Fix the type contract, add precise
  annotations, or adjust typed dependencies/configuration instead.
- Do not use mocking unless it is necessary to isolate external hardware,
  network services, or time-sensitive behavior. Prefer local simulators and
  real SQLite test databases.
- Add tests only when they exercise real logic.

### Important Conventions

1. **No f-strings in logging**: use `logger.info("msg %s", var)` instead of
   `logger.info(f"msg {var}")`.
   - Reason: deferred interpolation keeps disabled log levels cheap and lets
     logging handlers preserve structured arguments.

2. **Function-style tests only**: write `def test_*()` functions, not test
   classes.
   - No `TestBase` classes or complex test inheritance.
   - Use fixtures from `conftest.py`; prefer local in-file fixtures when the
     fixture is specific to one module.

3. **Database connections**: use context managers when practical and commit
   explicitly.
   - Connections use `sqlite3.Row` for dict-like row access.
   - Enable foreign keys with `conn.execute("PRAGMA foreign_keys = ON;")`.

4. **Environment variables**:
   - `PYTEST=1`: running under pytest.
   - `TEST_DB_NAME`: test database path used by subprocess tests.
   - `DB_PATH`: application SQLite database path.
   - `TEMPERATURE_BOT_CONFIG`: config YAML path.
   - `AE200_SIMULATOR=1`: use AE-200 simulator data.
   - `AIRTHINGS_SIMULATOR=1`: use Airthings simulator behavior.
   - `AQICN_SIMULATOR=1`: use local AQICN sample data instead of
     `api.waqi.info`.

5. **Error handling**: log errors with context and use appropriate log levels.

## Quality Gates

`make check` is non-mutating and runs static analysis, template/JS checks,
type checking, and Flyway migration validation. `make format` is the explicit
target for automated Ruff fixes.

`make test` runs Python tests with coverage and JavaScript unit tests.

## Configuration

Important environment variables:

- `DB_PATH`: SQLite database path. The Makefile defaults to `var/db/temperature-bot.db`.
- `DEV_DB`: development DB path used by migration targets.
- `TEMPERATURE_BOT_CONFIG`: YAML config path.
- `AE200_SIMULATOR=1`: use AE-200 simulator data.
- `AIRTHINGS_SIMULATOR=1`: use Airthings simulator behavior.
- `AQICN_SIMULATOR=1`: use local AQICN sample data instead of `api.waqi.info`.
- `PYTEST=1`: set by pytest configuration.

`temperature-bot-config.yaml` can contain production secrets and must not be
committed.

## Task Tracking

GitHub Issues are the canonical tracker for durable project work, regardless of
who is driving the session. Read `doc/agent-workflow-simson.md` before
tracking, creating, updating, or closing work.

David may still use Beads as a personal/local working queue. Beads entries are
not authoritative project records. Do not create, close, or rely on Beads issues
for project tracking unless the user explicitly asks for local Beads
housekeeping; for that narrow case, read `doc/agent-workflow-david.md`. When
multiple developers share the Beads queue (branch/PR flow, `bd dolt`
push/pull, JSONL conflict handling), follow
`doc/beads-multi-dev-workflow.md`.

`.beads/` is intentionally kept in the Git repo so agents can read and review
David's local or historical queue. Keep `.beads/issues.jsonl`, metadata, and
hooks tracked when David updates them. Do not delete or mutate `.beads/` unless
the user explicitly asks. Ignore auto-injected beads / `bd prime` session
context when choosing project work.

## External Services

- Hubitat Maker API
- Mitsubishi AE-200
- Airthings cloud API
- AQICN and AirNow
- Google APIs for optional spreadsheet integration
