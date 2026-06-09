# SQL Migrations with Flyway

Temperature Bot now tracks SQL schema versions with Flyway.

## Baseline schema

- `etc/flyway/sql/V1__baseline_schema.sql` is the baseline migration.
- It is based on the current `etc/schema.sql`.
- `flyway_schema_history` is the table used to track applied Flyway versions.

## Validate migrations

Run validation before applying migrations:

```bash
flyway \
  -locations=filesystem:etc/flyway/sql \
  -url=jdbc:sqlite:var/db/temperature-bot.db \
  validate
```

## Apply migrations

Run migrations:

```bash
flyway \
  -locations=filesystem:etc/flyway/sql \
  -url=jdbc:sqlite:var/db/temperature-bot.db \
  migrate
```

## Adding a new migration

1. Add a new SQL file in `etc/flyway/sql/`.
2. Use a Flyway versioned filename, for example:
   - `V2__add_new_table.sql`
   - `V3__add_alert_indexes.sql`
3. Run `flyway validate` and then `flyway migrate`.
