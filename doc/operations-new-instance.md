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
| `slg1.basistech.net` | 8003 | `slg1_basistech_net.service` | `/home/simsong/temperature-bot` | `simsong` | selectable — see below |
| `deg1.basistech.net` | 8004 | `deg1_basistech_net.service` | `/home/deg/temperature-bot` | `deg` | selectable — see below |

Ports, app directories, service accounts, and `DB_PATH` in this table are read
from the checked-in unit files in `etc/*.service`, which must be copied to
`/etc/systemd/system/` by hand.

**All four instances run on one physical machine.** `air.basistech.net`,
`slg1.basistech.net`, staging, and `deg1.basistech.net` are the same host under
different DNS names, service accounts, and ports. Ports are therefore a shared
resource, and CPU and memory pressure from one instance is felt by all of them —
including production. Deploying to a "test" instance is not free of production
risk.

`slg1` and `deg1` are parallel developer instances — one playground each, `slg1`
for Simson and `deg1` for David. They differ only in DNS name, port, service
account, and home directory. Neither is more authoritative or more "staging"
than the other, and neither is inherently a sandbox: each selects its database
through `DB_PATH` in its own unit file, and can point at the live production
database or at a private copy. See "Choosing which database a developer instance
uses" below.

Consequences worth internalizing before touching anything:

- **Read the installed unit before assuming which database an instance is on.**
  `/etc/systemd/system/<unit>` is what runs; the copy in `etc/` is only what was
  last committed, and the two drift. An instance pointed at
  `/var/db/temperature-bot.db` is another front end on live production data.
- **Pointing at production is not read-only.** The web app writes — changelog
  entries, rules-disable timers, device metadata — and SQLite in WAL mode needs
  write access to the database and its directory even to read.
- These instances are *not* independent host-capacity tests, because they share
  the machine with production. Watch aggregate CPU and memory, not just the one
  process.
- `doc/tech-debt.md` records a promotion order of local → `deg1` → `slg1` →
  `air` for changes under review. Read that as a sequence for staged review, not
  as a difference in kind between the two developer instances. Deployment to
  `air` is human-authorized and human-executed; agents are not authorized to
  deploy to `slg1` or `air`.

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

A developer instance — `slg1` or `deg1` — should run the web service only, with
no runner cron entries. Rules changes are shadow-only on both and must not send
commands until a human approves the cutover (`doc/tech-debt.md`).

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

## Choosing which database a developer instance uses

`slg1` and `deg1` each select their database with `DB_PATH` in their unit file.
Switching between the live production database and a private copy is routine:
production data makes a change realistic, a private copy makes it safe. This
section is the procedure for both instances — substitute the account, port, and
unit name from the inventory table.

### 1. Get a database to point at

Skip this when switching *to* production. To take a private copy, run this on
the server:

```bash
mkdir -p /home/deg/temperature-bot/var/db
sqlite3 /var/db/temperature-bot.db \
  ".backup '/home/deg/temperature-bot/var/db/temperature-bot.db'"
```

`.backup` is the right tool here: production is written every minute, and it
takes a consistent snapshot where `cp` can capture a torn page.

If reading `/var/db/temperature-bot.db` requires `sudo`, `chown` the copy to the
service account afterwards. A root-owned copy leaves the instance unable to
write it, which surfaces as the permission failure described below rather than
as anything mentioning ownership.

`make fetch-dev-db` also produces this layout, but it is built for a developer
laptop — it rsyncs `air.basistech.net:/var/db/` (the same machine, when run on
the server) and passes `--delete`, so it will remove anything else living in the
target directory. Prefer `.backup` on the server itself.

A copy is a fork, not a view: it stops receiving new readings the moment it is
made, and nothing written through it reaches production.

### 2. Point the unit at it

Edit the instance's unit in `etc/` so the change is versioned rather than only
live, then install it:

```bash
# Edit etc/deg1_basistech_net.service so exactly one DB_PATH line is active:
#   Environment="DB_PATH=/home/deg/temperature-bot/var/db/temperature-bot.db"
sudo cp -f etc/deg1_basistech_net.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart deg1_basistech_net.service
```

Two cautions on this step:

- **`daemon-reload` before `restart`**, or systemd restarts the old definition
  and the instance silently keeps using the previous database.
- **A repo edit becomes a dirty working tree.** `make deploy` starts with
  `git pull --ff-only`, which refuses to run when an incoming commit also
  touches the file you edited — and, when it does not, silently leaves your
  edit in place, so the checkout quietly diverges from the branch instead.
  Either commit the change, or use a systemd drop-in instead —
  `/etc/systemd/system/deg1_basistech_net.service.d/db.conf` containing a
  `[Service]` section with the `Environment=` line — which overrides the unit
  without touching the repository. A drop-in also keeps one developer's
  playground state out of shared history; the tradeoff is that the setting is
  then invisible to anyone reading `etc/`.

### 3. Verify the switch took

```bash
systemctl show deg1_basistech_net.service -p Environment   # which DB_PATH is live
curl -m 10 -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8004/
ss -ltn 'sport = :8004'
sudo journalctl -u deg1_basistech_net.service -e -n 100
```

`systemctl show` is the authoritative answer to "which database is this instance
actually using" — it reflects what systemd loaded, including any drop-in, rather
than what a file on disk says.

In the `ss` output, `Recv-Q` on a *listening* socket is the number of connections
that finished the TCP handshake and are queued waiting for the application to
accept them; it should be `0`. A number that stays above zero means the workers
are wedged — blocked on a database they cannot open, for example — and are no
longer accepting connections, even though the port is still open and systemd
reports the service as active.

Expect the dashboard to show different data after the switch. Confirm you are
looking at the instance you think you are by checking its port directly rather
than its URL — nginx is believed to route unmatched server names to production
(see the unverified nginx section above), so a misconfigured name can quietly
show you production instead.

### Failure modes to expect

- **The instance does not come up, and the journal names a schema mismatch.**
  Most likely the database is older than the code. `app/main.py` calls
  `validate_database_schema_on_startup()` while building the Flask app, which
  refuses to serve against a stale schema and exits instead. This is the guard
  working. Migrate the copy with
  `flyway migrate -url="jdbc:sqlite:<path>" -locations="filesystem:etc/flyway/sql"`
  and restart. This is the guard working, not a bug.
- **Permission denied on the database.** The service account must be able to
  write both the database file *and* its directory — WAL mode creates `-wal` and
  `-shm` siblings. `deg1` runs as `deg`, so pointing it at `/var/db/` requires
  that account to have write access there; check before assuming a read-only
  front end is possible.
- **An empty file where the database should be.** Anything that starts the app
  against a missing or empty database gets a schema bootstrapped from
  `etc/schema.sql` with no Flyway history — see the warning in step 6 of the
  bring-up. Delete it and take the copy again.

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
