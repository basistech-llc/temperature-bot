# Alert rules

Alert rules monitor equipment and sensors without changing them. They run once
per normal runner cycle even when the master HVAC Rules switch is off. HVAC
action rules remain subject to the master and per-device rule switches.
An Airthings request or payload-validation failure is logged but does not stop
that cycle's alert evaluation, reminders, or recovery notifications. The
collector validates the complete response before writing any device rows.

Action rules require an outdoor AQI observation no more than two hours old.
Missing, future-dated, or stale AQI stops the entire action-rule pass before any
equipment command is evaluated; the runner logs the reason. Explicit AQI values
supplied to the dry-run report remain available for scenario testing.
After compilation, an evaluation, contract, or command failure is isolated to
the affected device so later devices still run. Committed passes also write the
exception type and message to `changelog` for auditability.

`bin/rules.py` contains the two rule entry points:

- `run_rules_for_device()` returns HVAC actions.
- `run_alert_rules_for_device()` returns typed alert conditions.

The runner compiles this file once per cycle and shares the resulting typed
entry points between monitoring and action rules. The Rules forecast page also
compiles once per request rather than once per scenario cell.

Alert conditions have three states: `active`, `inactive`, and `indeterminate`.
Stale, missing, malformed, or incomplete sensor input is indeterminate rather
than recovered. An indeterminate result does not open a new alert. If the alert
was already active, it remains active and receives cadence-based reminders that
the current input cannot establish recovery. Fresh changed input is required to
close it.

The first alert rule detects a stuck Airthings monitor when all eight reported
measurements remain exactly unchanged for `AIRTHINGS_STUCK_SECONDS` (10 minutes
by default). The database layer compares normalized JSON values and follows a
continuous run across `devlog`'s 20-minute run-length-encoding boundaries. The
scan is bounded by `ALERT_RULE_HISTORY_SECONDS`, which defaults to the stuck
threshold, so a long-running alert does not rescan its entire history each
minute. The latest reading is fetched separately so stale input is still
reported as indeterminate rather than missing.

Every device returned by the Airthings API is evaluated. The collector persists
`device_type=SENSOR` and fills an unset `device_subtype=AIRTHINGS`; an existing
subtype is never overwritten. The `aqi_mon` metadata flag only controls indoor-
air-quality display and does not opt a sensor out of alerts.

AE-200 `ErrorSign`, `FilterSign`, and `CheckWater` observations enter the same
lifecycle and delivery pipeline. `ON` triggers or reminds, `OFF` resolves, and
a missing or unknown value is indeterminate so it cannot falsely recover an
active equipment alert.

## Lifecycle and delivery

An active condition creates one row in `alerts`. A partial unique index enforces
one active row per device and alert type, including across overlapping runners.
Each notification creates an
`alert_events` row before Slack delivery, then records whether delivery was
sent or failed and saves Slack's message timestamp. Recovery closes the active
alert, logs a `resolved` event, and sends a recovery message.

`alert_events` is also the durable Slack outbox. At the start of every committed
alert-rule cycle, pending and retryable failed events are attempted in bounded
batches. Each attempt is claimed in the database before network I/O so
overlapping runners do not normally send the same event. Failures use
exponential backoff from 1 minute to 1 hour, honor a longer Slack `Retry-After`,
and become terminal after 24 attempts. Recovery events remain retryable after
their active alert is closed. As with any at-least-once outbox, Slack may receive
a duplicate if it accepts a message and the process dies before recording the
successful response.

While a condition remains active, reminders are logged and sent:

- every 5 minutes through the first hour;
- every hour through the first 24 hours;
- every 4 hours thereafter.

These boundaries start at the initial persisted notification, not at a
historical sensor condition's `start_time`, so a newly detected old condition
still receives the first-hour cadence.

The Slack client reads `secrets.slack.token` and `secrets.slack.channel` from
`temperature-bot-config.yaml`; `SLACK_TOKEN` and `SLACK_CHANNEL` environment
variables override those values.
