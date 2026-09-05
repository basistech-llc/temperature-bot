# Handoff notes for DEG

Looks like I'll be touching this only at the end of each month, so stashing notes, thoughts, and
open tabs here:

## Current status — verified 2026-09-04 22:46 EDT

- Draft [PR #253](https://github.com/basistech-llc/temperature-bot/pull/253)
  prepares the `1.0.0b1` release workflow. Beta implementation commit
  `c3f85599bc8a508a75137ae0100c019d72a460da` passed all CI checks. Copilot's
  22:46 EDT review identified mutable source inputs, unchecked systemd
  drop-ins, and incomplete runtime-policy preflight. The current branch freezes
  a root-owned source checkout before unprivileged builds, rejects drop-ins,
  and verifies database identity, scheduler mode, and every integration mode;
  its focused updater suite passes, while current-head CI and re-review remain
  pending.
- `air-stage` is live-control staging, not a simulator. It is running
  `1.0.0b1-c3f85599bc8a`, with every integration simulator disabled and its
  collection scheduler enabled. The installed branch updater built, staged,
  activated, and health-checked that release successfully.
- Production remains on `0.11.0` at `7a7d2e53b32b` and was not changed by the
  staging validation.
- `slg1` and `deg1` share immutable developer release
  `0.11.0-5ffc51e31536`. Both socket-activated services are running in simulator
  mode with all integrations simulated, distinct private database identities,
  and scheduling disabled. Their ports are 8003 and 8004, respectively.
- There is no periodic release-updater unit installed on the host. Release
  updates begin only when an operator invokes the installed updater command.

Application releases and host configuration are separate transactions. The
package may carry reviewed systemd, socket, environment, and nginx files for
verification, but its installer does not write `/etc`, reload systemd/nginx, or
change enablement. Do not deploy by pulling a server checkout; follow
[`doc/release-and-deploy.md`](release-and-deploy.md) and
[`doc/DEPLOYMENT.md`](DEPLOYMENT.md).

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

The database snapshot endpoint is reachable only on the company VPN. Running
`make fetch-dev-db` in the next step checks that path without requiring SSH.

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
   - Simulator mode does not require `temperature-bot-config.yaml` or live credentials.
   - Live mode requires separately managed configuration, VPN access, and an
     intentional decision to reach real hardware.

**Running the Web Server**

Two flavors, both serve Flask on `http://localhost:8000` with `FLASK_DEBUG=True` and the local DB:

| Command | AE200 data | Needs Tailscale | Use when |
|---------|-----------|-----------------|----------|
| `make local-dev-sim`  | simulated (`AE200_SIMULATOR=1`) | no  | UI work, no hardware needed |
| `make local-dev-live` | live hardware                   | yes | seeing real device data |

`make local-dev` remains an alias for `make local-dev-sim`.

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
This downloads a consistent SQLite backup from the unauthenticated production
snapshot API over the VPN, verifies the response SHA-256, applies pending
Flyway migrations, and shows row-count stats. It writes only the database at
`var/db/temperature_bot/temperature-bot.db`; it never downloads the production
configuration or its secrets.

Before fetching, an existing `var/db/temperature_bot` directory is moved to a
timestamped directory under `var/db/backups`.

The endpoint is intentionally unauthenticated at the application layer because
`air.basistech.net` resolves to the private VPN address. A VPN connection is
still required.

**Mitsubishi control panel**

(requires TailScale connection) https://10.2.1.20/control/index.html

**Testing**:

```bash
make test  # Runs both Python and JavaScript tests
make pytest  # Python tests only
```

Tests automatically use `AE200_SIMULATOR=1` via the `[tool.pytest.ini_options]` `env` list in `pyproject.toml` and `tests/conftest.py`.


# Operations reference

## Endpoint inventory

- `air.basistech.net`: production on loopback port 8100
- `air-stage.basistech.net`: live-control staging on loopback port 8101
- `slg1.basistech.net`: simulator-only developer UI on loopback port 8003
- `deg1.basistech.net`: simulator-only developer UI on loopback port 8004

### nginx config

- Sites are in /etc/nginx/sites-available symlinked to /etc/nginx/sites-enabled
- Logs are in /var/logs/nginx/
- Test config: `sudo nginx -t`
- Restart: `sudo systemctl restart nginx`
- Test status: `sudo systemctl status nginx`

### Developer service diagnostics

```bash
curl --fail http://127.0.0.1:8004/api/v1/version
sudo systemctl status deg1_basistech_net.socket deg1_basistech_net.service
sudo journalctl -u deg1_basistech_net.service -e -n 200
```

## Open deployment work

- [#213](https://github.com/basistech-llc/temperature-bot/issues/213): validated immutable GitHub Releases
- [#215](https://github.com/basistech-llc/temperature-bot/issues/215): outbound host-side release polling
- [#216](https://github.com/basistech-llc/temperature-bot/issues/216): transactional migration and rollback activation
- [#217](https://github.com/basistech-llc/temperature-bot/issues/217): deployment preflight, live smoke tests, and provenance
- [#218](https://github.com/basistech-llc/temperature-bot/issues/218): production/staging/developer runtime isolation

Issue [#252](https://github.com/basistech-llc/temperature-bot/issues/252) is
closed: the selected `air-stage` policy is live control with all integration
simulators disabled. Activation must continue to reject future drift from that
policy.
