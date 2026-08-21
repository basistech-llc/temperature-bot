# SQL Migrations with Flyway

Temperature Bot now tracks SQL schema versions with Flyway.

## Baseline schema

- `etc/flyway/sql/V1__baseline_schema.sql` is the baseline migration.
- It contains only application-owned schema objects and matches the deployed pre-Flyway database.
- `etc/flyway/sql/V2__changelog_device_logtime_index.sql` upgrades the changelog device index to the current application schema.
- `etc/flyway/sql/V7__devlog_temperature_device_logtime_index.sql` adds the device-first partial index used by per-device temperature queries.
- `etc/flyway/sql/V8__devlog_temperature_logtime_device_index.sql` adds the time-first partial index used by multi-device chart boundary probes.
- `etc/flyway/sql/V9__fcu_owned_rooms.sql` gives every existing FCU one owned
  room, resets non-FCU devices to Unassigned, and adds uniqueness constraints
  for FCU ownership and assignment.
- `etc/flyway/sql/V10__room_presence.sql` stores room-at-observation presence
  events and indexes current and historical room queries.
- `etc/flyway/sql/V11__devlog_latest_device_reading_index.sql` indexes each
  device's newest logged reading.
- `etc/flyway/sql/V12__alert_events.sql` adds the durable record of alert
  notifications and Slack delivery outcomes. Slack's message `ts` is an opaque
  decimal identifier stored as `TEXT` so no precision is lost.
- `etc/flyway/sql/V13__alert_delivery_outbox.sql` adds attempt counts, Unix
  timestamps for last and next attempts, and explicit terminal state so failed
  Slack notifications can be retried safely across runner processes.
- `etc/flyway/sql/V14__device_subtype.sql` adds nullable device discovery
  metadata used to identify Airthings sensors without relying on display names.
- `etc/flyway/sql/V15__unique_active_alert.sql` closes older duplicate active
  alert rows and enforces one active lifecycle per device and alert type.
- `etc/flyway/sql/V16__changelog_action.sql` gives each activity-log row a
  machine-readable action. It also identifies the duplicate, comment-free Unix
  timestamps written by the former web control flow as rules suspensions while
  leaving genuinely ambiguous historical values classified as `legacy`.
- `etc/flyway/sql/V17__ae200_command_log.sql` stores the latest and historical
  AE-200 write requests, parsed controller acknowledgements, and failures. Unix
  times are integer milliseconds; request and response JSON use SQLite `TEXT`
  storage with `json_valid()` constraints.
- `etc/flyway/sql/V18__ae200_notifications.sql` stores unsolicited AE-200
  `notifyRequest` observations without claiming which actor caused the change.
- `etc/flyway/sql/R__performance_samples.sql` adds integration and network
  timing samples. It is repeatable so it can be deployed before or after the
  independent branch that owns V12-V15; see `doc/performance-monitoring.md`.
- Flyway creates and manages `flyway_schema_history`; do not add that table to a versioned migration or to `etc/schema.sql`.
- Existing populated databases are baselined at V1 by `make migrate-db` and `make deploy`, then any later migrations are applied.
- `etc/schema.sql` is generated from the Flyway migration history for tests and compatibility. Do not hand-edit it for schema changes.

## Make targets

| Target | Description |
|---|---|
| `make make-dev-db` | Delete and recreate the local dev DB by running all Flyway migrations from scratch. |
| `make migrate-db` | Apply any pending Flyway migrations to the **existing** local dev DB (safe to run on a populated database). |
| `make schema` | Regenerate `etc/schema.sql` by applying all migrations to a temp DB and dumping the application schema. |
| `make validate-migrations` | Apply all migrations to a temp DB and run `flyway validate`. |
| `make deploy` | Pull latest code, install dependencies, validate production Flyway state, back up the production DB, migrate, and validate again. |

## Validate migrations

Use the Makefile gate for local and CI validation:

```bash
make validate-migrations
```

To validate an existing database manually after it has been baselined or migrated:

```bash
flyway \
  -locations=filesystem:etc/flyway/sql \
  -url=jdbc:sqlite:var/db/temperature-bot.db \
  validate
```

## Apply migrations

Run migrations (use `make migrate-db` for the dev database, or `make deploy` for production):

```bash
flyway \
  -locations=filesystem:etc/flyway/sql \
  -url=jdbc:sqlite:var/db/temperature-bot.db \
  -baselineOnMigrate=true \
  migrate
```

## Adding a new migration

1. Add a new SQL file in `etc/flyway/sql/`. Normally use the next versioned
   migration. Use a repeatable migration only when the change is idempotent and
   branch-order compatibility requires it; document that decision in the SQL.
2. Use a Flyway versioned filename, for example:
   - `V3__add_new_table.sql`
   - `V4__add_alert_indexes.sql`
3. Run `make schema` to regenerate `etc/schema.sql` so CI picks up the new schema.
4. Run `make validate-migrations` and then `make migrate-db` (dev) or `make deploy` (production).

## Production deploy safeguards

`make deploy` is intended to run only on `slg1` by default. It:

1. Pulls the latest code in `/home/air/temperature-bot`.
2. Installs Poetry dependencies.
3. Validates already-applied migrations against
   `/var/db/temperature-bot.db`, allowing only migrations that are pending.
4. Copies the DB to `/var/db/temperature-bot-backups/temperature-bot.<UTC timestamp>.db`.
5. Applies pending migrations with `-baselineOnMigrate=true`.
6. Runs `flyway validate` again.

The final validation is strict. Allowing `*:pending` is limited to the
read-only preflight because pending migrations are the normal reason to run a
deployment; failed, missing, or checksum-mismatched applied migrations still
stop the deployment before the backup or migration.

Override `DEPLOY_HOSTNAME`, `DEPLOY_APP_DIR`, `DEPLOY_DB`, or
`DEPLOY_BACKUP_DIR` only
when intentionally targeting a different installation.

## Staging deploy

`make deploy-stage` updates `/home/air-stage/temperature-bot` with a fast-forward
pull, installs its dependencies, and creates a consistent SQLite backup of the
production database at `/home/air-stage/var/db/temperature-bot.db.new`. Flyway
migrates and validates that temporary database before the target briefly stops
the staging service, atomically replaces its database, and restarts the service.
The staging Gunicorn service listens on `127.0.0.1:8101` and never migrates or
writes through the production database.

The current deploy target does not stop the every-minute writer and uses a
filesystem copy rather than SQLite's consistent backup API. Until GitHub issues
tracking those deploy safeguards are resolved, a rooms migration must be
performed in a maintenance window: stop the cron runner, verify no runner is
active, create a consistent `sqlite3 ... .backup` snapshot, run the migration
and smoke checks, and only then restart the runner.

To roll back a room migration, stop all writers again, preserve the failed
database for diagnosis, restore the complete pre-migration SQLite backup
(including its Flyway history), deploy the matching pre-migration application
revision, validate it, and then resume the runner. Do not attempt to reverse V9
or V10 with ad hoc `ALTER TABLE` statements.

## Future release promotion

Production deployment should move to a staged release-promotion model. Prepare
the candidate code in an isolated, versioned release directory; migrate a
consistent copy of the production database; and run browser, collector, rules,
and database smoke tests against `air-stage.basistech.net`. Production remains
on its current checkout and database throughout that verification.

At cutover, quiesce production writers, take a fresh consistent database
backup, apply the already-tested migrations to that fresh database, and switch
an application symlink or equivalent release pointer atomically. Restart and
smoke-test production before resuming writers. Rollback must restore both the
previous release pointer and its matching database backup.

Do not promote the older staging database itself: production data can change
while staging is being verified. The candidate code and tested migration
sequence are promoted, then applied to a fresh production snapshot during the
short cutover window.
