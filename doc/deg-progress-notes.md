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
      - http://10.2.3.51/dashboards insufficiently good dashboard
      - http://10.2.3.51/installedapp/configure/520/mainPage new hickory dashboard
    - Documentation: https://docs2.hubitat.com/en/home
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
   - Runs via `wsgi.py`/gunicorn (production) or `flask --app app.main:app run` (dev, auto-reload —
     see `make local-live-dev` / `make local-dev`)

2. **SQLite Database** (`app/db.py`): Central data store
   - **Run-length encoding**: Temperature data stored with `(logtime, duration)` to avoid bloat when values don't change
   - **Tables**: `devices`, `devlog` (temperature logs), `aqi` (air quality), `alerts`, `changelog`
   - Flyway migrations in `etc/flyway/sql/` are canonical. `etc/schema.sql` is a generated compatibility schema; use `make schema`, `make validate-migrations`, and `make migrate-db` rather than hand-editing schema SQL.

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
- **Dependencies**: uv-managed (Python 3.12+)

The system runs continuously: `runner.py` collects data every minute, rules adjust fan speeds based on AQI/time, and the web interface provides monitoring and manual control.

### Running Locally on Dev Machine

**Initial Setup** (one-time):

1. **Install dependencies**:
   ```bash
   make install-macos  # or install-ubuntu on Linux
   ```
   This installs uv, creates a virtual environment, and installs all dependencies from `uv.lock`.


2. **Connect**

To do anything with the live system, you will need to first login with Tailscale for access.

The SSH password for the server is in Bitwarden (entry: `slg1.basistech.net`). Note that
`air.basistech.net` and `slg1.basistech.net` are the **same machine** — the Makefile defaults to
`air` (`FETCH_HOST`), but either name works.

Easiest way to confirm Tailscale is actually connected: just run `make fetch-dev-db` (next step).
If it pulls the DB successfully, your connection is good.

3. **Create local database**:
   ```bash
   make make-dev-db
   ```
   Creates a fresh `var/db/temperature_bot/temperature-bot.db` from the schema.

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

Two flavors, both serve Flask on `http://localhost:8000` with `FLASK_DEBUG=True` and the local DB:

| Command | AE200 data | Needs Tailscale | Use when |
|---------|-----------|-----------------|----------|
| `make local-dev`      | simulated (`AE200_SIMULATOR=1`) | no  | UI work, no hardware needed |
| `make local-live-dev` | live hardware                   | yes | seeing real device data |

The web interface needs a populated DB to show anything useful (see `make fetch-dev-db`).

**Note:** `FLASK_DEBUG` auto-reloads **Python** changes only — it does **not** reload JavaScript.
For JS changes, hard-reload the browser (shift-reload), or use node for live JS reload.


**Running the Data Collector/Rules Engine**

This polls the devices, fetches AQI, runs the rules engine, and logs everything to the DB.

Against **live hardware** (needs Tailscale):
```bash
make live-dev-runner   # runs bin/runner.py, no simulator
```

Against the **simulator** (no hardware/Tailscale needed):
```bash
AQICN_SIMULATOR=1 AE200_SIMULATOR=1 make every-minute
```
`make every-minute` runs `python -m bin.runner` with Makefile defaults (e.g. `DB_PATH`)
already set, which is why it is preferred over invoking `bin/runner.py` directly.
Note: set `AQICN_SIMULATOR=1` to avoid a live AQICN API call.

**Environment Variables**:

- `DB_PATH`: Database file path. The Makefile defaults it to `var/db/temperature_bot/temperature-bot.db` via
  `export DB_PATH ?= ...`, so the `make` targets already have it set. Only set it explicitly to point
  at a *different* DB, or when running the app/flask/python directly (bypassing make).
- `AE200_SIMULATOR`: Set to `1` to use simulated AE200 devices instead of real hardware
- `TEMPERATURE_BOT_CONFIG`: Path to config YAML (default: `temperature-bot-config.yaml` in repo root)
- `LOG_LEVEL`: Logging level (DEBUG, INFO, etc.)

**Note**: For the default DB location, the `DB_PATH=var/db/temperature_bot/temperature-bot.db` prefix on `make`
commands is redundant — the Makefile already exports that default (`Makefile:23`). Prefixing it
anyway is harmless; it just re-sets the same value.

**Fetching Real Database for Testing**:

To get a copy of the production database with real data:
```bash
make fetch-dev-db
```
This streams a read-only SQLite dump over Tailscale/SSH from the server
(`air.basistech.net`, aka `slg1.basistech.net`), applies pending Flyway
migrations, and shows row-count stats. It pulls down **two** things:
- the database → `var/db/temperature_bot/temperature-bot.db`
- `temperature-bot-config.yaml` (with production secrets) → repo root

Before fetching, an existing `var/db/temperature_bot` directory is moved to a
timestamped directory under `var/db/backups`.

So this single step also covers the "Configure" step above — no separate config copy needed.
SSH normally uses your key. The `fetch-dev-db` target permits the normal SSH
password prompt as a fallback; if prompted, the password is in Bitwarden under
`slg1.basistech.net`.

**Mitsubishi control panel**

(requires TailScale connection) https://10.2.1.20/control/index.html

**Testing**:

```bash
make test  # Runs both Python and JavaScript tests
make pytest  # Python tests only
```

Tests automatically use `AE200_SIMULATOR=1` via the `[tool.pytest.ini_options]` `env` list in `pyproject.toml` and `tests/conftest.py`.


# Progress notes

## Config notes

- air.basistech.net runs on port 8100
- slg1.basistech.net runs on port 8003
- deg1.basistech.net will be on 8004

### nginx config

- Sites are in /etc/nginx/sites-available symlinked to /etc/nginx/sites-enabled
- Logs are in /var/logs/nginx/
- Test config: `sudo nginx -t`
- Restart: `sudo systemctl restart nginx`
- Test status: `sudo systemctl status nginx`

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
- Do we have any automation for deploying `<repo>/etc/*.service` to `/etc/systemd/system/*.service`?

## Todo

- Move /etc/nginx config files to git in <repo>/etc
- Write tooling to keep live nginx and systemctl files in sync with repo
