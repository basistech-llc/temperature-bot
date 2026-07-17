# Alert rules

Alert rules monitor equipment and sensors without changing them. They run once
per normal runner cycle even when the master HVAC Rules switch is off. HVAC
action rules remain subject to the master and per-device rule switches.
An Airthings request or payload-validation failure is logged but does not stop
that cycle's alert evaluation, reminders, or recovery notifications. The
collector validates the complete response before writing any device rows.

`bin/rules.py` contains the two rule entry points:

- `run_rules_for_device()` returns HVAC actions.
- `run_alert_rules_for_device()` returns typed alert conditions.

The first alert rule detects a stuck Airthings monitor when all eight reported
measurements remain exactly unchanged for `AIRTHINGS_STUCK_SECONDS` (10 minutes
by default). The database layer compares normalized JSON values and follows a
continuous run across `devlog`'s 20-minute run-length-encoding boundaries. It
only evaluates recently observed readings, so a stopped runner or missing API
response is not misreported as repeated fresh data.

## Lifecycle and delivery

An active condition creates one row in `alerts`. Each notification creates an
`alert_events` row before Slack delivery, then records whether delivery was
sent or failed and saves Slack's message timestamp. Recovery closes the active
alert, logs a `resolved` event, and sends a recovery message.

While a condition remains active, reminders are logged and sent:

- every 5 minutes through the first hour;
- every hour through the first 24 hours;
- every 4 hours thereafter.

The Slack client reads `secrets.slack.token` and `secrets.slack.channel` from
`temperature-bot-config.yaml`; `SLACK_TOKEN` and `SLACK_CHANNEL` environment
variables override those values.
