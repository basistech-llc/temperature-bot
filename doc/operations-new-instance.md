# Operations: Standing Up a New Instance

How to bring up a new Temperature Bot deployment — a fresh host, or an
additional observation instance on the shared BasisTech server. For schema and
migration mechanics see `doc/sql-migrations.md`; for the AE-200 probe timer see
`doc/performance-monitoring.md`.

Most steps here are manual. `doc/tech-debt.md` and GitHub issues #31, #76, and
#180 track automating them. The "Not yet automated" section at the end lists
exactly what is missing so nobody has to rediscover it.

Provenance: everything about ports, service accounts, paths, database
locations, migrations, and Makefile behavior is read from the repository and is
as reliable as the repository is. The nginx section is the exception — it is
derived from `doc/deg-progress-notes.md`, which is exploratory personal notes
rather than a canonical record, and is marked unverified where it appears.

## Current instances

| Name | Port | Service unit | App dir | Runs as | `DB_PATH` |
|---|---|---|---|---|---|
| `air.basistech.net` | 8100 | `air_basistech_net.service` | `/home/air/temperature-bot` | `simsong` | `/var/db/temperature-bot.db` |
| staging | 8101 | `air-stage_basistech_net.service` | `/home/air-stage/temperature-bot` | `simsong` | `/home/air-stage/var/db/temperature-bot.db` |
| `slg1.basistech.net` | 8003 | `slg1_basistech_net.service` | `/home/simsong/temperature-bot` | `simsong` | `/var/db/temperature-bot.db` (**production DB**) |
| `deg1.basistech.net` | 8004 | `deg1_basistech_net.service` | `/home/deg/temperature-bot` | `deg` | `/home/deg/temperature-bot/temperature-bot.db` |

Ports, app directories, service accounts, and `DB_PATH` in this table are read
from the checked-in unit files in `etc/*.service`, which must be copied to
`/etc/systemd/system/` by hand.

**All four instances run on one physical machine.** `air.basistech.net`,
`slg1.basistech.net`, staging, and `deg1.basistech.net` are the same host under
different DNS names, service accounts, and ports. Ports are therefore a shared
resource, and CPU and memory pressure from one instance is felt by all of them —
including production. Deploying to a "test" instance is not free of production
risk.

Three consequences worth internalizing before touching anything:

- `slg1` points at the **production database**. It is a second web front end on
  production data, not an isolated sandbox.
- `deg1` is the safe place to observe application changes first: it is the only
  instance with its own database. It is *not* an independent host-capacity test,
  because it shares the machine with production.
- The deployment order for any change is local → `deg1` → `slg1` → `air`
  (`doc/tech-debt.md`). Deployment to `slg1` and `air` is human-authorized and
  human-executed; agents are not authorized to deploy there.

## Prerequisites

- Tailscale connected (all hosts and the AE-200/Hubitat networks are behind it).
- SSH access to the server. The password is in Bitwarden under
  `slg1.basistech.net` if key auth is not set up.
- `sudo` on the target host, for systemd and nginx.
- A copy of `temperature-bot-config.yaml`. It contains live API credentials and
  is **not** in the repository.

## Standing up a new instance

### 1. Choose the instance identity

Pick, and write down, all of these before starting:

- instance name and DNS name;
- a free port on `127.0.0.1` (existing: 8003, 8004, 8100, 8101);
- service account and app directory;
- absolute `DB_PATH`;
- `TEMPERATURE_BOT_INSTANCE` — a stable environment label used by performance
  sampling (`production`, `staging`, …; defaults to the hostname).

### 2. Clone the repository

```bash
git clone <remote-url> <app-dir>
cd <app-dir>
```

The repository is `basistech-llc/temperature-bot`. Get the exact remote string
with `git remote -v` on a working instance rather than copying one from here —
existing checkouts use a machine-specific SSH host alias
(`git@github.com-basis:…`) defined in `~/.ssh/config`, which will not resolve
elsewhere.

The service account needs its own SSH key registered with GitHub, or use an
HTTPS clone if the instance only ever pulls.

### 3. Install dependencies

```bash
make install-ubuntu    # or install-macos
```

This installs pipx, Poetry (pinned by `POETRY_VERSION`), and the in-project
`.venv`. It also runs `playwright install --with-deps`, which pulls Chromium and
a large apt dependency set — a server instance does not need a browser, so
consider skipping that step by hand on a host where it matters.

### 4. Install Flyway

**`make install-ubuntu` does not install Flyway**, and nothing else on a host
does either. Install it explicitly, matching the version CI pins
(`FLYWAY_VERSION` in `.github/workflows/cicd.yml`, currently `12.8.1`):

```bash
FLYWAY_VERSION=12.8.1
FLYWAY_TAR="flyway-commandline-${FLYWAY_VERSION}-linux-x64.tar.gz"
curl --fail --location --output "/tmp/${FLYWAY_TAR}" \
  "https://github.com/flyway/flyway/releases/download/flyway-${FLYWAY_VERSION}/${FLYWAY_TAR}"
sudo mkdir -p /opt/flyway
sudo tar -xzf "/tmp/${FLYWAY_TAR}" -C /opt/flyway
sudo ln -sf "/opt/flyway/flyway-${FLYWAY_VERSION}/flyway" /usr/local/bin/flyway
flyway -v
```

On macOS use `macosx-arm64` or `macosx-x64` in place of `linux-x64`.

Without Flyway on `PATH`, `make check`, `make schema`, `make migrate-db`, and
`make deploy` all fail.

### 5. Install the configuration file

Copy `temperature-bot-config.yaml` from a working instance into the app
directory root, or point `TEMPERATURE_BOT_CONFIG` at it. It supplies the
location, Hubitat host and app id, AE-200 host, and the `secrets:` block
(AirNow, Hubitat, Google air quality, AQICN, Airthings).

Never commit this file. `make fetch-dev-db` is the sanctioned way to pull it to
a development machine.

### 6. Create the database with Flyway — before starting the service

```bash
sudo mkdir -p "$(dirname <DB_PATH>)"
flyway migrate \
  -url="jdbc:sqlite:<DB_PATH>" \
  -locations="filesystem:etc/flyway/sql"
```

Or seed from a production snapshot instead, which carries its Flyway history
with it:

```bash
sqlite3 /var/db/temperature-bot.db ".backup '<DB_PATH>'"
```

> **Order matters.** If the Flask app or the runner starts against a missing or
> empty database, `app/db.py` bootstraps it from the generated
> `etc/schema.sql` — which produces a current schema with **no
> `flyway_schema_history` table**. A later `flyway migrate
> -baselineOnMigrate=true` then baselines that database at V1 and tries to apply
> V2 onward against objects that already exist. `V12__alert_events.sql` creates
> a table without `IF NOT EXISTS`, and `V13`/`V14` are bare `ALTER TABLE ... ADD
> COLUMN`, so the migration fails partway and leaves a database needing `flyway
> repair`. Always create the database with Flyway first.

Confirm the history table exists before going further:

```bash
sqlite3 <DB_PATH> "SELECT version, description, success FROM flyway_schema_history ORDER BY installed_rank;"
```

### 7. Install the systemd unit

Start from the closest unit in `etc/` and adjust `User`, `Group`,
`WorkingDirectory`, `PATH`, `DB_PATH`, the bind port, and
`TEMPERATURE_BOT_INSTANCE`.

```bash
sudo cp -f etc/<instance>_basistech_net.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now <instance>_basistech_net.service
sudo systemctl status <instance>_basistech_net.service
sudo journalctl -u <instance>_basistech_net.service -e -n 200
```

Review the unit before installing it. The checked-in units are not uniform:
some force `LOG_LEVEL=DEBUG` and `--log-level debug`, and all compute workers as
`2 * nproc + 1`. Issue #180 covers making these production-safe; do not
reinstall a debug configuration on a production host.

### 8. Configure nginx

> **Unverified section.** nginx configuration is **not in this repository**, and
> nothing here was checked against the live server. The layout below comes from
> `doc/deg-progress-notes.md`, which is exploratory personal notes — not
> canonical and not guaranteed current. Read the running configuration on the
> server and correct this section when someone does.

- Site files in `/etc/nginx/sites-available/`, symlinked into `sites-enabled/`.
- Proxy the DNS name to `127.0.0.1:<port>`.
- Access and error logs under `/var/log/nginx/`.
- `sudo nginx -t` then `sudo systemctl restart nginx`.

Copy the site file of an existing instance for the TLS/certificate stanzas and
change the DNS name and proxy port. The BasisTech certificates are not managed
by anything in this repository.

Ignore `etc/setup_ubuntu.bash`. It is stale exploratory scripting: it configures
Apache rather than nginx, misspells `nginx` as `ngix` in three commands, and
installs a `basistech_air.service` unit that no longer exists.

An unresolved question from the same notes: something in `/etc/nginx` routes
unmatched names to `air.basistech.net` by default. A new instance may appear to
"work" while actually serving production until its own site file is enabled.
Verify you are hitting the new instance by checking its port directly and by
watching its journal, not just by loading the URL.

### 9. Decide whether this instance collects data — usually it should not

The per-minute runner does more than read: it executes the rules engine and
issues real fan-speed and drive commands to the AE-200. **Only one instance may
run it.** A second collector will fight production for control of the hardware.

An observation instance such as `deg1` should run the web service only, with no
runner cron entries. Rules changes are shadow-only on `deg1` and `slg1` and must
not send commands until a human approves the cutover (`doc/tech-debt.md`).

If this instance genuinely is the collector, the production cron entries are
recorded as comments in the Makefile (`Cron targets` section) and cover the
per-minute runner, the hourly AQI fetch, and the daily compaction. The AE-200
network probe is packaged as
`etc/temperature-bot-performance-monitor.{service,timer}`; see
`doc/performance-monitoring.md`. Use the timer or the cron entry, never both.

### 10. Verify

```bash
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:<port>/
sudo systemctl status <instance>_basistech_net.service
sudo journalctl -u <instance>_basistech_net.service -e -n 200
flyway validate -url="jdbc:sqlite:<DB_PATH>" -locations="filesystem:etc/flyway/sql"
```

Then load the site through nginx and confirm the dashboard renders. Watch CPU
and memory for a few minutes — the shared machine hosts several instances, and
worker counts are generous.

## Deploying to an existing instance

`make deploy` is written for production. It refuses to run unless the hostname
matches `DEPLOY_HOSTNAME` (default `slg1`), then pulls, installs dependencies,
and runs `deploy-flyway` (validate → timestamped backup → migrate → validate).

For any other instance every path must be overridden, since the defaults point
at production:

```bash
make DEPLOY_HOSTNAME="$(hostname)" \
     DEPLOY_APP_DIR=/home/deg/temperature-bot \
     DEPLOY_DB=/home/deg/temperature-bot/temperature-bot.db \
     DEPLOY_BACKUP_DIR=/home/deg/temperature-bot-backups \
     deploy
```

Setting `DEPLOY_HOSTNAME="$(hostname)"` makes the wrong-machine guard
unconditionally pass, so check `DEPLOY_DB` twice before running it. A dedicated
per-instance target with fixed values would be safer, and is listed below as
missing automation.

`make deploy-stage` is the only fully automated non-production path, and its
account, paths, and service name are hardcoded to `air-stage`.

After deploying, restart the instance's service — `make deploy` does not:

```bash
sudo systemctl restart <instance>_basistech_net.service
```

## Rollback

Flyway Community has no `undo`. The only rollback is the file backup taken
before the migration.

1. Stop every writer: the instance service, and the runner cron entries if this
   instance collects.
2. Preserve the failed database for diagnosis; do not overwrite it.
3. Restore the complete pre-migration backup from `<DEPLOY_BACKUP_DIR>`,
   including its Flyway history.
4. Check out the matching pre-migration revision and `poetry install`.
5. `flyway validate` against the restored database.
6. Restart the service and the collector.

Do not attempt to reverse a migration with ad hoc `ALTER TABLE` statements.

Record the prior commit, the unit file, the backup path, and the exact rollback
command **before** changing a production host.

## Not yet automated

Known gaps, so they can be planned rather than rediscovered:

- **Flyway install and version.** No install target provides it; CI pins
  `12.8.1` but hosts and developer machines use whatever is present, or nothing.
  A developer following `README.md` hits `flyway: command not found` at the end
  of `make check`.
- **Application schema bootstrap bypasses Flyway.** `app/db.py` applies
  `etc/schema.sql` to an empty database, producing no Flyway history. See the
  warning in step 6.
- **Service files.** `etc/*.service` must be hand-copied to
  `/etc/systemd/system/`; nothing validates that a host's installed unit matches
  the repository. Issues #31 and #180.
- **nginx configuration** is not in the repository at all.
- **Cron entries** exist only as Makefile comments.
- **No per-instance deploy targets.** `make deploy` is gated to `slg1` with
  production paths; `make deploy-stage` is hardcoded to `air-stage`.
- **Inconsistent service accounts and paths** across the checked-in units.
  Issue #76 proposes a single deploy user.
- **Backups use `cp`** on a live, continuously written SQLite database, rather
  than `sqlite3 .backup`. `deploy-stage` does this correctly; `deploy-flyway`
  does not.
