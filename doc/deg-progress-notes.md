## Notes to self

Looks like I'll be touching this only at the end of each month, so stashing notes, thoughts, and
open tabs here:

- VPN for BasisTech: Tailscale, installed on MacBook deg-mac-2023
- Site links:
  - [main site](https://air.basistech.net/)
  - [Simson's clone](https://slg1.basistech.net/)
  - [David's clone](https://deg1.basistech.net/)
  - [local](http://localhost:8000/)
  - Hubitat:
    - Dashboard: http://10.2.3.51/
      - http://10.2.3.51/dashboards insufficently good dashboard
      - http://10.2.3.51/installedapp/configure/520/mainPage new hickory dashboard
    - Documentation: https://docs2.hubitat.com/en/home
- Database: Often useful to copy latest database from /var/db on server to each instance. Placed in
  root or var/db.
- Raw view of [Mitsubishi HVAC](http://10.2.1.20/control/index.html). Credentials in
  Bitwarden. Nominal manual [here](http://10.2.1.20/en/maintenance.html) but requires insecure Java
  browser.
- [Git repo](https://github.com/basistech-llc/temperature-bot)
- [ChatGPT project](https://chatgpt.com/g/g-p-68f5f96a17a081918d4bb454409e6602-temperature-bot/project)
- [Maps and other CALA operations notes](https://drive.google.com/drive/folders/1bEr7AV2xa5vEsoc0z8lx5yMtcLWnAdGs)
- [ClickHouse DB](https://clickhouse.com/)
- Related project: [Home Assistant](https://home-assistant.basistech.net/)
- CSS tooling used in this project: [pure.css](https://pure-css.github.io/)
- Other notes in Git repo and Slack with Simson


# Memory Refresh

*Quick overview of how the system works when returning after a break. Everything you need to get back to speed on things that were muscle-memory last month.*

## Temperature Bot Project Overview

**Purpose**: Monitors and controls HVAC devices (AE200 ERV units and Hubitat temperature sensors) with automated rules based on time, AQI, and conditions.

### Architecture

**Core Components**:

1. **Flask Web Application** (`app/main.py`): Serves web UI and REST API
   - Web routes (`routes_web.py`): HTML pages (index, rules, logs, device details)
   - API routes (`routes_api.py`): JSON endpoints for status, temperature series, fan/drive control
   - Runs via `wsgi.py` (production) or `run_local.py` (dev with auto-reload)

2. **SQLite Database** (`app/db.py`): Central data store
   - **Run-length encoding**: Temperature data stored with `(logtime, duration)` to avoid bloat when values don't change
   - **Tables**: `devices`, `devlog` (temperature logs), `aqi` (air quality), `alerts`, `changelog`
   - Schema auto-applied from `etc/schema.sql` on connection

3. **Rules Engine** (`app/rules_engine.py` + `bin/rules.py`):
   - Python code in `bin/rules.py` executed dynamically
   - Accesses device IDs, time variables (HOUR, DAY, AQI), and functions `set_drive()`, `set_fan_speed()`
   - Can disable rules globally or per-device for a duration (default 3 hours after manual changes)

4. **Device Integrations**:
   - **AE200** (`app/ae200.py`): ERV units via WebSocket/XML protocol. Controls fan speed (0-4) and drive (on/off). Simulator mode if `AE200_SIMULATOR=1`
   - **Hubitat** (`app/hubitat.py`): Temperature sensors via REST API
   - **Air Quality** (`app/airquality.py`): AQI from aqicn.org API

5. **Periodic Runner** (`bin/runner.py`): Runs every minute (via cron/systemd)
   - Polls AE200 devices → logs temperature + status to `devlog`
   - Polls Hubitat → logs temperatures
   - Fetches AQI → stores in `aqi` table
   - Runs rules engine (if not disabled)
   - Daily cleanup: compresses old data (5-min intervals for week-old, 20-min for month-old)

### Data Flow

1. **Collection**: `runner.py` → queries devices → `db.insert_devlog_entry()` (RLE compression)
2. **Rules**: `runner.py` → `rules_engine.run_rules()` → executes `bin/rules.py` → calls `set_fan_speed()`/`set_drive()` → updates AE200 devices
3. **Display**: Web UI → API endpoints → database queries → JSON/HTML rendering

### Configuration

- **`temperature-bot-config.yaml`**: Location, Hubitat host/appId, AE200 host, API keys
- **Environment**: `DB_PATH` (database location), `AE200_SIMULATOR` (testing mode)

### Key Features

- **RLE compression**: Prevents database growth when temperatures are stable
- **Alert tracking**: Monitors ErrorSign, FilterSign, CheckWater from AE200 devices
- **Rules disable**: Manual changes disable rules for 3 hours (configurable)
- **Temporal queries**: API supports `?start=` and `?end=` for time ranges

### Development

- **Testing**: pytest with `AE200_SIMULATOR=1` environment variable
- **Linting**: ruff, mypy, pylint configured in `pyproject.toml`
- **Dependencies**: Poetry-managed (Python 3.12+)

The system runs continuously: `runner.py` collects data every minute, rules adjust fan speeds based on AQI/time, and the web interface provides monitoring and manual control.

### Running Locally on Dev Machine

**Initial Setup** (one-time):

1. **Install dependencies**:
   ```bash
   make install-macos  # or install-ubuntu on Linux
   ```
   This installs Poetry, creates a virtual environment, and installs all dependencies.
   
   
2. **Connect**

To do anything with the live system, you will need to first login with Tailscale for access.

3. **Create local database**:
   ```bash
   make make-dev-db
   ```
   Creates a fresh `var/db/temperature-bot.db` from the schema.
   
   Or, and usually preferred, clone the live database
   
   ```bash
   make fetch-dev-db
   ```
   
   Clone a snapshot of the live DB locally.

4. **Configure**:
   - Copy `temperature-bot-config.yaml` and fill in your values (or use existing one)
   - For simulator mode, you don't need real Hubitat/AE200 credentials
   - For live mode, you'll need VPN access (Tailscale) and real credentials

**Running the Web Server**

```bash
DB_PATH=var/db/temperature-bot.db make local-dev
```

This runs the Flask app on `http://localhost:8000` with:
- `AE200_SIMULATOR=1` (uses test data instead of real AE200 devices)
- `FLASK_DEBUG=True` (auto-reload on code changes)
- Database at `var/db/temperature-bot.db`

The web interface will be available but won't have real device data unless you've populated the
database.

Alternatively, you can run against the live hardware (but still using a local copy of the DB) by
connecting with TailScale and:

```bash
DB_PATH=var/db/temperature-bot.db make live-dev-web
```

[old?] Or: `DB_PATH=var/db/temperature-bot.db FLASK_DEBUG=True poetry run python run_local.py`
(without `AE200_SIMULATOR`)


**Running the Data Collector/Rules Engine**

```bash
DB_PATH=var/db/temperature-bot.db make live-dev-runner
```

Or manually:
```bash
export DB_PATH=var/db/temperature-bot.db
export AE200_SIMULATOR=1
poetry run python bin/runner.py
```

This will:
- Poll simulated AE200 devices
- Fetch AQI (real API call)
- Run rules engine
- Log everything to the database

Or, you can run against the live hardware with

   ```bash
   DB_PATH=var/db/temperature-bot.db make live-dev-runner
   ```
   Or: `DB_PATH=var/db/temperature-bot.db poetry run python bin/runner.py` (without `AE200_SIMULATOR`)

**Environment Variables**:

- `DB_PATH`: **Required** - Database file path (e.g., `var/db/temperature-bot.db`). Must be set explicitly or the app will fail to start.
- `AE200_SIMULATOR`: Set to `1` to use simulated AE200 devices instead of real hardware
- `TEMPERATURE_BOT_CONFIG`: Path to config YAML (default: `temperature-bot-config.yaml` in repo root)
- `LOG_LEVEL`: Logging level (DEBUG, INFO, etc.)

**Note**: `DB_PATH` must be set explicitly for all commands. The Makefile doesn't export it automatically, so you need to prefix commands with `DB_PATH=var/db/temperature-bot.db`.

**Fetching Real Database for Testing**:

To get a copy of the production database with real data:
```bash
make fetch-dev-db
```
This copies the database from `slg1.basistech.net` to `var/db/** and shows stats.

**Mitsubishi control panel**

(requires TailScale connection) https://10.2.1.20/control/index.html

**Testing**:

```bash
make test  # Runs both Python and JavaScript tests
make pytest  # Python tests only
```

Tests automatically use `AE200_SIMULATOR=1` via `tests/conftest.py`.


# Progress notes

## Config notes

- air.basistech.net runs on port 8100
- slg1.basistech.net runs on port 8003
- deg1.basistech.net will be on 8004

### nginx config

- Sites are in /etc/nginx/sites-available symlinked ti /etc/nginx/sites-enabled
- Logs are in /var/logs/nginx/
- Test config: `sudo nginx -t`
- Restart: `sudo systemctl restart nginx`
- Test status: `sudo systemctl status nginx`

### Local dev config

- `make install-macos`
- `make make-dev-db`
- `make local-dev`
- `make test` (some tests currently fail)

To run the runner locally, you'll need a filled-in temerature-bot-config.yaml

### deployments config

- `git pull ...`, after setting up .ssh
- `make install-ubuntu`
- `<repo>/etc/*.service` has the service control files for each copy
- Each needs to be copied manually into /etc/systemd/system
- Start service with, e.g.,

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now deg1_basistech_net.service
```

- See logs:

```
sudo systemctl status deg1_basistech_net.service
sudo journalctl -u deg1_basistech_net.service -e -n 200
```

## Questions

- in /etc/nginx, what is causing default routing to air.basistech.net (e.g. of deg1, before I
    configured it). Is this desirable behavior, or more confusing than it is worth?
- Do we have any automation for deploying <repo>/etc/_\_service to /etc/systemd/system/_.service?

## Todo

- Move /etc/nginx config files to git in <repo>/etc
- Write tooling to keep live nginx and systemctl files in sync with repo

## Currently stuck on
