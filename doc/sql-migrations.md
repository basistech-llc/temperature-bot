# SQL Migrations with Flyway

Temperature Bot now tracks SQL schema versions with Flyway.

## Baseline schema

- `etc/flyway/sql/V1__baseline_schema.sql` is the baseline migration.
- It is based on the current `etc/schema.sql`.
- `flyway_schema_history` is the table used to track applied Flyway versions.

## Make targets

| Target | Description |
|---|---|
| `make make-dev-db` | Delete and recreate the local dev DB by running all Flyway migrations from scratch. |
| `make migrate-db` | Apply any pending Flyway migrations to the **existing** local dev DB (safe to run on a populated database). |
| `make schema` | Regenerate `etc/schema.sql` by applying all migrations to a temp DB and dumping its schema. |
| `make deploy` | Pull latest code, install dependencies, **and** run `flyway migrate` against the production DB. |

## Validate migrations

Run validation before applying migrations:

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
   - `V2__add_new_table.sql`
   - `V3__add_alert_indexes.sql`
3. Run `make schema` to regenerate `etc/schema.sql` so CI picks up the new schema.
4. Run `flyway validate` and then `make migrate-db` (dev) or `make deploy` (production).
