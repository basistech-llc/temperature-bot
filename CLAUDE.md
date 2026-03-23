# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Flask-based home automation monitoring app for temperature sensors, HVAC control, and air quality. Collects data from Hubitat hub, AE200 HVAC controller, and Airthings sensors, stores in SQLite (dev) / ClickHouse (prod), and provides a web UI for visualization and control.

## Commands

```bash
make install-macos      # Install dependencies (Homebrew → pipx → Poetry)
make local-dev          # Run dev server with AE200 simulator + hot-reload
make test               # Python + JavaScript tests with coverage
make pytest             # Python tests only (coverage in htmlcov/)
make test-js            # JavaScript unit tests (Node.js)
make check              # All linters: ruff, pylint, djlint, eslint
make check-types        # mypy type checking
make make-dev-db        # Create fresh dev database from schema
make fetch-dev-db       # Pull production DB + config from remote server
make every-minute       # Run data collection (normally runs via cron)
make daily              # Daily cleanup and RLE aggregation

# Single test file / test
poetry run pytest tests/test_db.py -v
poetry run pytest tests/test_db.py::test_function_name -v
```

## Architecture

**Data flow:** Hardware sources → `bin/runner.py` (cron, every minute) → SQLite → Flask web UI + JSON APIs

**Hardware integrations:**
- `app/hubitat.py` — REST API to Hubitat hub (temperature/humidity sensors)
- `app/ae200.py` — WebSocket + Modbus TCP to AE200 HVAC controller; set `AE200_SIMULATOR=1` to use mock data from `app/test_data/`
- `app/airthings.py` — Airthings cloud API (air quality: radon, CO2, VOC)
- `app/airquality.py` — Outdoor AQI from AQICN and AirNow APIs

**Data storage design:**
- Temperatures stored as `temp10x` (integer = temp × 10 Celsius) in `devlog` table
- Run-length encoding: consecutive readings at same temperature are merged into a single row with extended `duration`. `bin/runner.py:combine_temp_measurements()` handles this.
- `changelog` table provides audit trail for all manual HVAC changes
- Schema lives in `etc/schema.sql`; no migration framework — production changes are manual ALTER statements

**Rules engine** (`app/rules_engine.py`, `bin/rules.py`): Auto-controls HVAC based on temperature, AQI, and time-of-day. Rules are Python code evaluated at runtime. Can be disabled globally or per-device (default: 3 hours via `RULES_DISABLE_SECONDS`). Virtual device `"rules_engine"` in `devices` table controls global enable/disable.

**Web layer:** Server-side rendering (Jinja2) for initial structure; JavaScript adds live updates, ECharts time-series charts, and Tabulator tables. Pages should be functional without JS. Route handlers in `routes_web.py` (UI) and `routes_api.py` (`/api/v1/*`).

## Coding Conventions

- **No f-strings in logging**: `logger.info("msg %s", var)` — required for performance and log level filtering
- **Function-style tests only**: `def test_*()` functions, never test classes
- **Database connections**: Use context managers, explicit commit, enable foreign keys (`PRAGMA foreign_keys = ON;`), use `sqlite3.Row` factory
- **Pylint threshold**: Must score ≥ 9.5/10
- Keep route handlers thin — business logic belongs in `db.py`, `rules_engine.py`, or integration modules

## Test Fixtures (conftest.py)

- `empty_database_conn` — empty SQLite DB (no data)
- `test_database_conn` — schema applied, no data
- `test_database_conn_with_test_data` — schema + sample data across 4 time intervals
- `flask_test_client` — Flask test client with overridden DB connection
- `skip_on_github` — marker to skip tests in CI

Browser (Playwright) tests are opt-in; most tests use Flask test client only.

## Task Tracking

Use `bd` (beads) for all task tracking — never markdown TODOs. See `AGENTS.md` for workflow details.
