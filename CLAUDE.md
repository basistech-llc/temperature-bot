# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Read `AGENTS.md` and `.github/copilot-instructions.md` for full coding conventions, project structure, and workflow details.**

Run tests through the Makefile. For a single pytest target:

```bash
make PYTEST_ARGS=tests/test_db.py::test_function_name pytest
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
- Flyway migrations in `etc/flyway/sql/` are the canonical schema history. `etc/schema.sql` is generated from those migrations with `make schema`; do not hand-edit it for schema changes.

**Rules engine** (`app/rules_engine.py`, `bin/rules.py`): Auto-controls HVAC based on temperature, AQI, and time-of-day. Rules are Python code evaluated at runtime. Can be disabled globally or per-device (default: 3 hours via `RULES_DISABLE_SECONDS`). Virtual device `"rules_engine"` in `devices` table controls global enable/disable.

**Web layer:** Server-side rendering (Jinja2) for initial structure; JavaScript adds live updates, ECharts time-series charts, and Tabulator tables. Pages should be functional without JS. Route handlers in `routes_web.py` (UI) and `routes_api.py` (`/api/v1/*`).

## Task Tracking

This project does not use `bd` (beads). Do not run `bd` commands or rely on
`.beads/` state; follow the current user request and Git/GitHub workflow only
when explicitly asked.
Any `.beads/` documentation in the repository is legacy and should be ignored.
