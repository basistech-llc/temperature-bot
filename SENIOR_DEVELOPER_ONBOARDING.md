# Temperature Bot - Senior Developer Onboarding Report

## Executive Summary

**Temperature Bot** is an automated HVAC control system for BasisTech LLC that monitors temperature sensors and air quality, then dynamically controls Energy Recovery Ventilators (ERVs) based on configurable Python rules. The system collects data from Hubitat IoT devices and AE-200 HVAC controllers, stores time-series data in SQLite with run-length encoding, and provides a Flask web dashboard for monitoring and manual control.

## Project Overview

### Purpose

Automate HVAC control for energy efficiency and air quality management by:

- Collecting temperature data from multiple sensors every minute
- Monitoring outdoor Air Quality Index (AQI) from aqicn.org
- Executing time-based and air-quality-based rules to control ERV fan speeds
- Providing a web interface for monitoring and manual override
- Maintaining historical data for analysis

### Tech Stack

- **Backend**: Python 3.12+, Flask web framework
- **Database**: SQLite3 with run-length encoding for temperature data compression
- **Hardware Integration**:
  - Hubitat IoT platform (temperature sensors)
  - AE-200 HVAC controllers via WebSocket
- **Deployment**: Gunicorn with systemd on Ubuntu
- **Testing**: pytest with Playwright for browser automation
- **Development Tools**: Poetry, Ruff, pylint, mypy, djlint

## Architecture

### System Components

1. **Flask Web Application** (`app/main.py`)

    - Serves web dashboard and REST API
    - Modular route structure (API in `routes_api.py`, web in `routes_web.py`)
    - Runs on port 8100 behind reverse proxy

2. **Periodic Runner** (`bin/runner.py`)

    - Runs every minute via cron/systemd timer
    - Collects temperature data from Hubitat and AE-200
    - Updates AQI data
    - Executes automation rules
    - Performs daily data cleanup/coarsening

3. **Rules Engine** (`bin/rules.py` + `app/rules_engine.py`)

    - Python-based rules file that gets `exec()`ed
    - Access to device IDs, time variables, AQI
    - Can disable rules per-device or globally for specified duration
    - Rules automatically disabled for 3 hours after manual control

### Key Design Patterns

#### Run-Length Encoding for Temperature Data

-  Instead of inserting a new row every minute, extends the `duration` field if temperature and status unchanged
- Dramatically reduces database size
- Max duration: 1 hour before forcing new entry
- Implementation: `db.py::insert_devlog_entry()`

#### Simulator Pattern

- AE-200 controller can run in simulator mode via `AE200_SIMULATOR` env var
- Loads test data from `app/test_data/ae200_*.json`
- Enables development without hardware access
- Critical for CI/CD and local testing

#### Async/Sync Hybrid

- AE-200 uses WebSockets (async), but wrapped with `AsyncRunner` for sync contexts
- `runner.run_async_safely()` handles both event loop and non-event-loop contexts

## Database Schema

**4 Main Tables** (`etc/schema.sql`):

```sql
devices          # Device registry with name, AE200 mapping, rules disable state
  device_id (PK), device_name, ae200_device_id, disabled_until, notes

devlog           # Temperature/status log with run-length encoding
  log_id (PK), device_id (FK), logtime, duration, temp10x, status_json

changelog        # Audit log of all control changes
  changelog_id (PK), logtime, device_id (FK), unit, ipaddr,
  current_values, new_value, agent, comment

aqi              # Air quality index time series
  logtime, aqi, co, h, no2, o3, p, pm10, pm25, so2, t, w
```

**Key Design Notes**:

- Temperature stored as `temp10x` (Celsius \* 10) for integer precision
- `status_json` stores full device state as JSON blob
- `disabled_until` is Unix timestamp; 0 = enabled
- AQI table stores full IAQI breakdown from aqicn.org

## Project Structure

```
temperature-bot/
├── app/                      # Main application package
│   ├── main.py              # Flask app factory
│   ├── db.py                # Database operations (600+ lines)
│   ├── rules_engine.py      # Rules execution logic
│   ├── routes_api.py        # REST API endpoints (/api/v1/*)
│   ├── routes_web.py        # Web page routes
│   ├── ae200.py             # AE-200 controller interface
│   ├── hubitat.py           # Hubitat IoT integration
│   ├── airquality.py        # AQI data from multiple sources
│   ├── weather.py           # US National Weather Service API
│   ├── templates/           # Jinja2 HTML templates
│   ├── static/              # JavaScript, CSS, echarts library
│   └── utils/               # Helper modules
├── bin/
│   ├── runner.py            # Main periodic data collector
│   ├── rules.py             # Business logic rules (exec'd)
│   └── scheduler.py         # Device monitoring tool
├── etc/
│   ├── schema.sql           # Database schema
│   ├── *.service            # Systemd unit files
│   └── data/                # Sample JSON payloads
├── tests/                   # Comprehensive pytest suite (54+ tests)
│   ├── test_*.py           # Test modules
│   └── helpers/            # Test utilities
├── pyproject.toml          # Poetry dependencies
└── Makefile               # Development tasks
```

## Key Files to Understand

### Core Application

- `app/main.py` - Entry point, Flask app creation
- `app/db.py` - All database logic, **critical for understanding data flow**
- `app/rules_engine.py` - How rules execute and disable mechanisms
- `bin/runner.py` - Periodic job orchestration
- `bin/rules.py` - **The actual business logic rules**

### Hardware Interfaces

- `app/ae200.py` - WebSocket communication with HVAC controllers
- `app/hubitat.py` - REST API calls to Hubitat hub

### Configuration

- Configuration via YAML file (location: `TEMPERATURE_BOT_CONFIG` env var or `temperature-bot-config.yaml`)
- Secrets stored in YAML or environment variables (env var takes precedence)
- See `app/util.py::get_config()` and `get_secret()`

## API Endpoints

### REST API (`/api/v1/*`)

- `GET /api/v1/status` - Current device status
- `GET /api/v1/temperature?device_ids=1,2&start=<unix>&end=<unix>` - Time series data
- `GET /api/v1/air_quality` - AQI time series
- `GET /api/v1/weather` - Current weather + AQI
- `GET /api/v1/logs` - Changelog with pagination
- `POST /api/v1/set_fan_speed` - Control fan (JSON body: `{device_id, fan_speed}`)
- `POST /api/v1/set_drive` - Control drive (JSON body: `{device_id, drive}`)
- `GET /api/v1/disable-rules?seconds=<int>` - Disable all rules

### Web Pages

- `/` - Main dashboard with current status
- `/chart` - Temperature/AQI charting (ECharts)
- `/rules` - View rules, test execution, disable controls
- `/logs` - Change history
- `/device_log/<id>` - Per-device detailed log

## Development Setup

### Prerequisites

```bash
# macOS
make install-macos

# Ubuntu
make install-ubuntu
```

This installs: pipx, poetry, ruff, and Playwright browsers.

### Local Development

```bash
# Install dependencies
poetry install

# Run with live reload and simulator
make local-dev
# or manually:
FLASK_DEBUG=True DB_PATH=var/db/temperature-bot.db AE200_SIMULATOR=1 python run_local.py
```

### Testing

```bash
# Run full test suite with coverage
make pytest

# Run specific test file
poetry run pytest tests/test_db.py -v

# Linting
make pylint    # Python
make djlint    # HTML templates
make eslint    # JavaScript
```

### Database Management

```bash
# Fetch production database (readonly operations)
make fetch-dev-db

# Recreate dev database from schema
make make-dev-db

# Extract schema from database
make etc/schema.sql
```

## Testing Philosophy

**Comprehensive Coverage** (54+ tests across 15 files):

- Unit tests for core modules (`test_db.py`, `test_ae200.py`)
- Integration tests (`test_endpoints.py`, `test_routes.py`)
- Browser automation tests (`test_browser_ux.py` with Playwright)
- Bin tools regression tests (`test_bin_tools.py`)

**Key Testing Features**:

- Simulator mode for hardware-independent tests
- Temporary SQLite databases per test
- Pytest fixtures for database states
- GitHub Actions CI/CD compatible

**Project-Specific Rules** (from `.cursorrules`):

- Function-style pytest tests only (no base classes)
- No f-strings in logging methods
- Local fixtures preferred over conftest.py dependencies

## Deployment

**Production Environment**:

- Ubuntu server with systemd
- Service: `air_basistech_net.service`
- Gunicorn with auto-worker scaling
- Database: `/var/db/temperature-bot.db`
- Runs behind nginx reverse proxy

**Cron Job** (every minute):

```bash
*/1 * * * * /path/to/.venv/bin/python -m bin.runner
```

## Rules Engine Deep Dive

**How Rules Work**:

1. `bin/rules.py` is plain Python with special globals injected
2. Available variables: device IDs (e.g., `ERV_KITCHEN`), time vars (`HOUR`, `TUESDAY`), `AQI`
3. Available functions: `set_drive(device_id, 0|1)`, `set_fan_speed(device_id, 1-4)`
4. Rules file is `exec()`ed with controlled namespace
5. Before executing commands, checks if device/global rules disabled

**Example Rule**:

```python
# Tuesday/Thursday lunch rush - high ventilation
if TUESDAY or THURSDAY:
    if HOUR in [11, 12]:
        kitchen_erv_speed = 4

# Poor outdoor air - reduce fresh air intake
if AQI > 100:
    kitchen_erv_speed = 0
    set_drive(ERV_KITCHEN, 0)  # Turn off
```

**Testing Rules**:

- `/rules` page shows rule preview for next 7 days across AQI thresholds
- `runner.py --rules test` - Test rules without execution
- `rules_engine.rules_results()` - Dry-run function

## Common Tasks

### Adding a New Device

1. Add device to Hubitat or AE-200 controller
2. Device auto-registers on first data collection
3. Update `bin/rules.py` if automation needed
4. Device ID constant appears in rules engine context

### Modifying Rules

1. Edit `bin/rules.py`
2. Test with `/rules` page or `runner.py --rules test`
3. Deploy (no app restart needed - rules re-read each execution)

### Investigating Issues

1. Check logs: systemd journal or syslog
2. Database query: `sqlite3 /var/db/temperature-bot.db`
3. Web interface `/logs` for change history
4. Per-device log: `/device_log/<device_id>`

### Adding API Endpoint

1. Add route to `routes_api.py` or `routes_web.py`
2. Use `@with_db_connection` decorator for automatic DB connection
3. Use Pydantic models for request validation (`flask_pydantic`)
4. Add corresponding test in `tests/test_endpoints.py`

## Important Gotchas

1. **Temperature stored as integers**: `temp10x` is Celsius \* 10
2. **Run-length encoding**: Queries must account for `logtime + duration`
3. **Rules disable mechanism**: Manual control disables rules for 3 hours (`RULES_DISABLE_SECONDS`)
4. **Simulator mode**: Always check `AE200_SIMULATOR` env var for tests
5. **Async wrappers**: AE-200 uses async, wrapped for sync contexts
6. **Config precedence**: Environment variables override YAML config
7. **No pytest classes**: Project uses function-style tests only

## Security Considerations

- Secrets via environment variables or config YAML (not committed)
- No authentication on web interface (internal network only)
- SQL injection protected (parameterized queries throughout)
- Rules engine uses controlled `exec()` namespace (no file system access)

## Performance Characteristics

- Database size: Run-length encoding keeps it manageable (months of data in MB)
- Runner execution: ~2-5 seconds per cycle
- API response times: <100ms for most endpoints
- Chart queries: Temporal quantification for large date ranges

## Future Considerations

- AQI storage in database (mentioned in TODO.md)
- Potential migration from SQLite to TimescaleDB for better time-series performance
- OAuth/authentication for web interface
- Mobile app or notifications
- Weather data correlation with temperature patterns

## Resources

- AE-200 Documentation: `doc/AE-200.pdf`
- Airthings API: `doc/airthings.md`
- Release Notes: `doc/RELEASE_NOTES.md`
- Bin Tools Testing: `tests/README_bin_tools.md`
- Sample data: `etc/data/*.json`, `app/test_data/*.json`

## Getting Help

- Codebase uses type hints extensively (mypy checked)
- Docstrings on most functions
- Test files serve as usage examples
- Inline comments for complex logic (especially in `db.py` and `rules_engine.py`)

---

**Next Steps**: Set up local development environment, run test suite, explore `/rules` page, and review `bin/rules.py` to understand business logic.
