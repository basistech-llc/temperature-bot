# Performance monitoring

## Purpose

The AE-200 does not expose controller CPU or queue utilization through the
interface used by Temperature Bot. This design records request latency and
failures as indirect controller-load signals and records independent network
measurements so WAN changes are not mistaken for AE-200 saturation.

Monitoring is observational. Production and staging keep their normal ability
to read and write the AE-200. No read-only application mode is introduced.

## Signals

### Application requests

Every real AE-200 operation records one sample:

- `get_devices`: enumerate controller units;
- `get_device_info`: fetch one unit's state;
- `set`: send a control command.

Durations use `time.perf_counter_ns()`, a monotonic clock, and are stored in
milliseconds:

- `connect_ms`: WebSocket TCP connection and HTTP upgrade;
- `response_ms`: XML send/receive time, including the AE-200 `setResponse` for
  control commands;
- `close_ms`: WebSocket close time;
- `total_ms`: the complete synchronous operation.

The schema retains the nullable `lock_wait_ms` column so historical samples
remain readable. AE-200 requests are no longer serialized, so new samples leave
this legacy field empty.

The row also records the operation, AE-200 device id when applicable, response
size, success or failure, normalized error type, instance/client identity, and
an optional experiment id. A monitoring write failure is logged but never
replaces the application request's return value or exception. Inline request
instrumentation uses a zero-wait SQLite transaction: if another writer holds
the database, the sample is dropped and a warning is logged instead of delaying
AE-200 work. Scheduled network probes may use SQLite's normal bounded wait
because they are not on a control-request path.

Simulator operations are not recorded as AE-200 performance samples because
they do not exercise the controller or network.

Every control write also creates a best-effort durable row in
`ae200_command_log`. This is distinct from performance timing: it records the
requested fields and a parsed high-level `setResponse`, or a bounded error. The
AE-200 diagnostics page displays the most recent 50 rows.

### Independent network probe

`python -m bin.performance_monitor --once` records three probes without issuing
an AE-200 XML command:

1. DNS resolution of the configured AE-200 hostname.
2. Three ICMP echo requests, summarized as minimum, median, maximum, and packet
   loss.
3. One TCP connection attempt to a configurable port expected to have no
   listener.

When DNS supplies both address families, the probe prefers IPv4. This keeps the
resolved literal compatible with the `ping` executable on both Linux and
macOS; an IPv6-only target is retained, but may require platform-specific
`ping6` support in a future extension.

The TCP probe intentionally measures a reject path. `ECONNREFUSED` means the
target was reached and promptly returned a TCP RST, so the sample is successful
with outcome `refused`. A timeout or unreachable error is a failed network
sample. If the supposedly closed port accepts the connection, the probe records
outcome `connected` and closes immediately; the operator should choose a
different port. This is not an HTTP probe: an HTTP measurement would require a
request and response, while an "empty HTTP connect" is only a TCP connection.

The default closed port is TCP/1 and is configurable with
`AE200_REJECT_PORT`. Network firewalls may silently drop that port instead of
rejecting it, so deployment must confirm the expected `refused` outcome.

The probe is a separate short-lived process, independent of the HVAC Rules
master switch. The checked-in
`etc/temperature-bot-performance-monitor.service` and `.timer` run it at 30
seconds past each minute so its measurements can be compared with the minute
collector. Install them in `/etc/systemd/system`, run `systemctl daemon-reload`,
and enable the timer with
`systemctl enable --now temperature-bot-performance-monitor.timer`. A staging
installation needs a copy or override with the staging working directory,
database, and instance id.

## Storage

Samples live in the append-only `performance_samples` table. They are not
added to AE-200 `status_json`: latency changes on nearly every request and
would defeat `devlog` run-length compression.

The schema is installed by the repeatable Flyway migration
`R__performance_samples.sql`. A repeatable migration is used deliberately
because this work branches from `main` at V11 while the independent AQI/alerts
branch owns V12 through V15. Flyway applies repeatable migrations after pending
versioned migrations, so this PR can deploy before or after that branch without
reusing a version number. Future changes after the branches converge should use
the next normal versioned migration.

The default retention period is 90 days. The daily runner deletes older rows;
`PERFORMANCE_RETENTION_DAYS` can tune the period. At the present baseline of 13
AE-200 WebSocket requests per minute, application samples contribute about
18,720 rows per day. The independent probe contributes three rows per minute,
or 4,320 rows per day.

## Identity and experiments

Set these environment variables on each deployment:

- `TEMPERATURE_BOT_INSTANCE`: stable environment name, such as `production` or
  `staging`; defaults to the hostname.
- `PERFORMANCE_CLIENT_ID`: process role, such as `minute-runner`, `web`, or
  `network-probe`; defaults to the executable name.
- `PERFORMANCE_EXPERIMENT_ID`: optional label shared by samples during a
  controlled test.
- `AE200_REJECT_PORT`: expected-closed TCP port; defaults to `1`.
- `AE200_WRITE_RESPONSE_TIMEOUT_SECONDS`: maximum time a control request waits
  for the AE-200 `setResponse`; defaults to `10` seconds. A timeout is recorded
  as a failed controller command and returned to the web client as HTTP 502.
- `PERFORMANCE_RETENTION_DAYS`: raw-sample retention; defaults to `90`.

Releases before issue #233 may leave `/tmp/temperature-bot-ae200.lock` behind.
Current code neither opens nor uses that file. It can be removed after all
Temperature Bot processes have been upgraded.

Production and staging write to their own SQLite databases. Each chart therefore
shows samples generated by that deployment. To compare the same interval across
both databases, export the query results or point a reporting tool at copies of
both databases; the application must not make staging write into production's
database.

## Chart and API

`/performance-monitoring` defaults to the last day and can select a week,
month, or custom date range. It plots raw latency for:

- AE-200 connect, command/response, and total time;
- ICMP median latency;
- TCP reject latency.

Filters distinguish instance, client, sample type, and operation. Failures and
unexpected outcomes remain in the API response and summary rather than being
dropped from the graph. `/api/v1/performance_samples` returns a typed
`{"samples": [...], "truncated": false}` page for the selected range, capped to
protect the web process from unbounded queries. The chart shows rolling p50 and
p95 AE-200 total latency over the latest 60 displayed request samples.
The 50,000-row default limit accommodates a full day at the expected load.
Broader ranges can reach the cap; the page reports truncation rather than
silently presenting the result as complete.

## Interpretation

No single latency value proves controller CPU saturation:

| Observation | Likely area to investigate |
|---|---|
| DNS, ICMP, TCP, and AE-200 all rise | WAN path or remote-site network |
| ICMP is stable; TCP and AE-200 rise | TCP path, firewall, or target host stack |
| DNS/ICMP/TCP are stable; AE-200 response rises | AE-200 application/controller |
| `connect_ms` is stable; `response_ms` rises | AE-200 XML processing |
| Probe is stable; only one client slows | client-specific queueing or code path |

Cross-data-center ICMP can be deprioritized, and a closed TCP port can be
filtered. Trends and correlated signals are more useful than a single sample.

## Controlled staging-load experiment

Staging remains writable so a maintainer can make a change and verify that the
AE-200 accepted it. To measure the cost of a second collector:

1. Establish at least one day of production baseline data.
2. Confirm the network probe normally reports `refused`, not timeouts.
3. Set a unique `PERFORMANCE_EXPERIMENT_ID` on the staging collector.
4. Start only the staging AE-200 collection loop at the normal one-minute rate;
   do not duplicate Hubitat, Airthings, weather, or automatic HVAC rules unless
   those systems are part of the test.
5. Keep staging web controls enabled for manual read/write validation.
6. Stop the experiment if error rate rises or p95 AE-200 response time degrades
   materially and stays elevated.
7. Compare before/during/after p50, p95, p99, failures, and network probes.

The experiment measures capacity indirectly. It does not establish AE-200 CPU
utilization unless Mitsubishi exposes a separate supported metric.
