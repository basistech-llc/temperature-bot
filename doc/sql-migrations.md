# SQL Migrations with Flyway

Temperature Bot now tracks SQL schema versions with Flyway.

## Baseline schema

- `etc/flyway/sql/V1__baseline_schema.sql` is the baseline migration.
- It contains only application-owned schema objects and matches the deployed pre-Flyway database.
- `etc/flyway/sql/V2__changelog_device_logtime_index.sql` upgrades the changelog device index to the current application schema.
- `etc/flyway/sql/V7__devlog_temperature_device_logtime_index.sql` adds the device-first partial index used by per-device temperature queries.
- `etc/flyway/sql/V8__devlog_temperature_logtime_device_index.sql` adds the time-first partial index used by multi-device chart boundary probes.
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

1. Add a new SQL file in `etc/flyway/sql/`.
2. Use a Flyway versioned filename, for example:
   - `V3__add_new_table.sql`
   - `V4__add_alert_indexes.sql`
3. Run `make schema` to regenerate `etc/schema.sql` so CI picks up the new schema.
4. Run `make validate-migrations` and then `make migrate-db` (dev) or `make deploy` (production).

## Production deploy safeguards

`make deploy` is intended to run only on `slg1` by default. It:

1. Pulls the latest code in `/home/air/temperature-bot`.
2. Installs Poetry dependencies.
3. Runs `flyway validate` against `/var/db/temperature-bot.db`.
4. Copies the DB to `/var/db/temperature-bot-backups/temperature-bot.<UTC timestamp>.db`.
5. Applies pending migrations with `-baselineOnMigrate=true`.
6. Runs `flyway validate` again.

Override `PROD_HOSTNAME`, `PROD_APP_DIR`, `PROD_DB`, or `PROD_BACKUP_DIR` only
when intentionally targeting a different installation.
