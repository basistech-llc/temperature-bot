# Scheduled Jobs with systemd

Temperature Bot's minute, hourly, and daily production jobs are defined as
separate systemd oneshot services and timers under `etc/systemd/`. They run as
the non-login `temperature_bot` account, share an OS lock, and log to journald.

| Timer | Schedule | Command |
|---|---|---|
| `temperature-bot-minute.timer` | every wall-clock minute | `bin.runner` |
| `temperature-bot-stage-minute.timer` | every minute, 5–20 seconds after production | `bin.runner --ae200-stage-collection` |
| `temperature-bot-hourly.timer` | 30 seconds after each hour | `bin.runner --aqi` |
| `temperature-bot-daily.timer` | 15 seconds after midnight | `bin.runner --daily` |

The offsets retain the historical cron timing. `Persistent=true` runs one
catch-up invocation after downtime; it does not replay every missed interval.
The three services use `/run/temperature-bot/writer.lock` so differently named
jobs cannot write concurrently. systemd also prevents a second instance of one
oneshot service while it is active.

Staging has a separate timer, writer lock, and database. Its 5-second base
offset plus a 0–15-second systemd random delay prevents synchronized AE-200
polling while keeping every staging run within the first 20 seconds of the
minute. The staging web application sends live equipment commands, while the
policy-guarded scheduled runner only reads AE-200 state; it does not evaluate
alerts, contact other integrations, or run HVAC rules.

## Install

The deployment package owns the canonical unit bytes. Before the complete
upgrade transaction exists, installation remains an explicit human operation:

```bash
sudo install -d -m 0750 -o root -g temperature_bot /etc/temperature-bot
sudo install -m 0640 -o root -g temperature_bot \
  etc/systemd/temperature-bot.env.example /etc/temperature-bot/runtime.env
sudo install -m 0644 etc/systemd/*.service etc/systemd/*.timer \
  /etc/systemd/system/
sudo systemd-analyze verify \
  /etc/systemd/system/temperature-bot-{minute,hourly,daily}.{service,timer}
sudo systemctl daemon-reload
sudo systemctl enable --now \
  temperature-bot-minute.timer \
  temperature-bot-hourly.timer \
  temperature-bot-daily.timer
```

Review `/etc/temperature-bot/runtime.env` before enabling anything. The
production database is `/var/db/temperature_bot/temperature-bot.db`; old
documentation and commented crontabs may name the retired hyphenated directory.
Do not enable the timers until the production web service and database
ownership issues in #76 and #218 have been resolved and verified.

Once a timer has completed successfully, remove the corresponding cron entry.
Never leave both schedulers enabled.

## Observe and operate

```bash
systemctl list-timers 'temperature-bot-*'
systemctl status temperature-bot-minute.timer temperature-bot-minute.service
journalctl -u temperature-bot-minute.service -e
sudo systemctl start temperature-bot-minute.service
sudo systemctl disable --now temperature-bot-minute.timer
```

Starting the service directly performs one immediate run without changing the
timer schedule.

## Deployment quiescence

Stopping a timer prevents future starts but does not stop an invocation that is
already running. Deployment therefore uses this order for every writer:

1. Record whether each timer is enabled and active.
2. Stop the minute, hourly, and daily timers.
3. Wait a bounded time for their services to become inactive; gracefully stop
   a remaining service and fail closed if it cannot stop.
4. Verify all scheduled services and other database writers are inactive.
5. Take and validate the SQLite rollback snapshot, migrate, activate, and run
   health checks.
6. Restore only the timers that were previously enabled/active, and only after
   success or completed rollback.

This is why the systemd migration is a deployment prerequisite: it provides an
explicit and auditable way to prevent the next every-minute poll while the
database is being backed up, migrated, or restored.

This PR versions and tests the units but does not install them or alter the live
host. Production rollout requires explicit authorization and live verification
of the effective units, processes, database, timers, and old crontabs.
