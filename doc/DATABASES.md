# Database Inventory

This is the live SQLite inventory for the Temperature Bot deployment on
`slg1`. It records which database each instance actually uses and separates
runtime databases from old working copies, snapshots, and tool caches.

The full inventory was last verified read-only on 2026-08-25 at 15:42 UTC.
The `slg1` and `deg1` runtime entries were re-verified during their simulator
deployment on 2026-08-29. The installed systemd units and running-process
environments are the source of truth; checked-in unit files describe intended
configuration and may differ from the host.

## Runtime databases

| Database | Consumer | Runtime state | Schema | Latest `devlog` (UTC) | Notes |
|---|---|---|---|---|---|
| `/var/db/temperature_bot/temperature-bot.db` | `air_basistech_net.service` and `air-stage_basistech_net.service`, both configured as `temperature_bot` | `air-stage` is running on `127.0.0.1:8100`; `air` is restart-looping because it tries to bind the same port | Flyway V18 | 2026-08-25 13:34:03 | Production database. Staging must not use it; tracked by #218. |
| `/home/deg/var/db/temperature-bot.db` | `deg1_basistech_net.service`, running as `deg` with database identity `deg1` | Simulator-only service on `127.0.0.1:8004`; scheduler disabled | Flyway V18 | 2026-08-25 13:34:03 | David's private copy. The directory and database are owned by `deg`; the pre-deployment backup is under `/home/deg/var/db/backups`. |
| `/home/simsong/var/db/temperature-bot.db` | `slg1_basistech_net.service`, running as `simsong` with database identity `slg1` | Simulator-only service on `127.0.0.1:8003`; scheduler disabled | Flyway V18 | 2026-08-13 09:34:02 | Simson's private copy, created with SQLite's backup API from the former checkout-local database. |

No scheduled collector currently uses a database. The `temperature_bot`
crontab contains only commented entries, and those comments still name the
retired `/var/db/temperature-bot.db` path. No Temperature Bot systemd timers
are installed.

## Non-runtime application databases

No effective systemd unit, active cron entry, or running process referenced
the files in this table during the audit.

| Database | Schema | Latest `devlog` (UTC) | Apparent purpose |
|---|---|---|---|
| `/var/db/temperature-bot.db` | Flyway V18 | 2026-08-25 13:34:03 | Retired production path. WAL and SHM files remain, as do references in `~` unit backups and commented cron lines. A read-only `PRAGMA quick_check` did not finish within 90 seconds; do not delete this file until retirement and recovery are verified. |
| `/home/air/temperature-bot/hold/temperature-bot.db` | Flyway V15 | 2026-08-12 13:50:03 | Held snapshot from before the V16-V18 migrations. |
| `/home/deg/temperature-bot/var/db/temperature-bot.db` | Flyway V15 | 2026-08-12 20:12:04 | David's former checkout-local working copy; superseded by `/home/deg/var/db/temperature-bot.db`. |
| `/home/simsong/temperature-bot/temperature-bot.db` | Pre-Flyway schema | 2026-02-17 16:54:43 | Simson's legacy checkout-root working copy. |
| `/home/air/temperature-bot/temperature-bot.db` | Empty SQLite database | — | Unused 4 KiB file at the application's fallback path. |
| `/home/air-stage/temperature-bot/temperature-bot.db` | Empty SQLite database | — | Unused 4 KiB file at the application's fallback path. |
| `/home/deg/air-backup/temperature-bot/temperature-bot.db` | Empty SQLite database | — | Unused 4 KiB file in an old checkout backup. |

The intended private staging path,
`/home/air-stage/var/db/temperature-bot.db`, does not exist. The installed
staging unit instead points at production.

## Backup and snapshot databases

These files had no runtime consumer. Matching sizes and timestamps do not prove
that separate copies are byte-identical or restorable; validate a chosen copy
before recovery.

The four legacy snapshot names below each exist in all three directories:

- `/var/db`
- `/home/deg/temperature-bot/var/db`
- `/home/simsong/temperature-bot/var/db`

| Filename | Copies | Schema | Latest `devlog` (UTC) | Use |
|---|---:|---|---|---|
| `temperature-bot.backup-2025-10-24.db` | 3 | Pre-Flyway schema | 2025-10-24 06:17:02 | Historical recovery snapshot. |
| `temperature-bot.backup-2026-02-19.db` | 3 | Pre-Flyway schema | 2026-02-19 12:20:03 | Historical recovery snapshot. |
| `temperature-bot.backup.2026-03-23.db` | 3 | Pre-Flyway schema | 2026-03-23 12:07:04 | Historical recovery snapshot. |
| `temperature-bot.backup.2026-03-24.db` | 3 | Pre-Flyway schema | 2026-03-24 12:41:03 | Historical recovery snapshot. |

The newer snapshot `temperature-bot.20260812T135122Z.db` exists once in each
of these backup directories:

- `/var/db/temperature-bot-backups`
- `/home/deg/temperature-bot/var/db/temperature-bot-backups`
- `/home/simsong/temperature-bot/var/db/temperature-bot-backups`

All three copies are Flyway V15 and have a latest `devlog` timestamp of
2026-08-12 13:51:04 UTC.

`/var/db/temperature-bot-backups/fetch-dev-db.20260821T121635Z.972929.db` is a
fourth newer snapshot. It is Flyway V15 with a latest `devlog` timestamp of
2026-08-13 09:34:02 UTC. Its name identifies it as an incomplete cleanup from
`make fetch-dev-db`; no consumer referenced it.

## Ancillary SQLite files

| Database | Contents | Consumer |
|---|---|---|
| `/home/air/temperature-bot/myapp/storage.db` | Legacy `log` table | No running process or surviving source file references it. |
| `/home/air-stage/temperature-bot/myapp/storage.db` | Legacy `log` table | No running process or surviving source file references it. |
| `/home/deg/air-backup/temperature-bot/myapp/storage.db` | Legacy `log` table | No running process or surviving source file references it. |
| `/home/simsong/temperature-bot/.mypy_cache/3.12/cache.db` | MyPy `files2` cache table | MyPy tooling only; not application data. |

The three `myapp` directories contain bytecode, editor backups, secrets files,
and `storage.db`, but no live Python source. They are not part of the current
repository application.

## Path aliases

These symlinks do not create additional databases:

| Alias | Resolves to | Consequence |
|---|---|---|
| `/home/air/temperature-bot/var` | `/var` | `/home/air/temperature-bot/var/db/...` is the same file as `/var/db/...`. |
| `/home/air-stage/temperature-bot/var` | `/var` | A path beneath the staging checkout's `var/db` would also reach `/var/db`; use `/home/air-stage/var/db` for a private staging database. |

## Operational rules

- Give every non-production service a private absolute `DB_PATH`. Only the
  production service and production collectors may use
  `/var/db/temperature_bot/temperature-bot.db`.
- Ensure the service identity can write the database's parent directory as well
  as the database, WAL, and SHM files. SQLite must be able to create, rename,
  and remove sidecars.
- Do not copy a live WAL-mode database with raw `cp` or `rsync`. Use SQLite
  `.backup`, the backup API, or `VACUUM INTO`, then run `PRAGMA quick_check` on
  the result.
- Do not rely on the checkout-root fallback `temperature-bot.db`; every service,
  timer, and cron job must set `DB_PATH` explicitly.
- Treat `~` systemd files and commented cron entries as stale references, not
  effective configuration. Verify with `systemctl show` and running-process
  environments.
- Quiesce writers and take a validated snapshot before moving, migrating,
  replacing, or deleting a runtime database.

## Read-only verification

The core live checks are:

```bash
systemctl show air_basistech_net.service air-stage_basistech_net.service \
  deg1_basistech_net.service slg1_basistech_net.service \
  -p Id -p ActiveState -p SubState -p User -p Group \
  -p WorkingDirectory -p Environment -p MainPID

sudo grep -R -HEn 'DB_PATH|temperature-bot\.db' \
  /etc/systemd/system /etc/cron.d /etc/crontab
sudo sh -c "grep -HEn 'DB_PATH|temperature-bot\.db' \
  /var/spool/cron/crontabs/*"

sudo find -P /var/db /home/air /home/air-stage /home/deg /home/simsong \
  -xdev -type f \( -iname '*.db' -o -iname '*.sqlite' \
  -o -iname '*.sqlite3' \) -path '*temperature-bot*'

sudo lsof -nP | grep -E 'temperature[-_]bot.*\.db(-wal|-shm)?$'
```

An application may close its SQLite connection between requests, so an empty
`lsof` result does not prove that a configured database is unused. Effective
unit and process environments are the primary consumer evidence.
