# Hubitat Information

This document describes how Temperature Bot talks to Hubitat, what must be set
up on the Hubitat side, how sensors are discovered, and how Hubitat readings
are stored.

## Source Map

- `app/hubitat.py`: Hubitat Maker API client, simulator support, and device
  control helpers.
- `bin/runner.py`: minute runner that polls Hubitat and writes readings.
- `app/db.py`: device creation, current status, time-series queries, and log
  compression.
- `app/room_config.py`: current static room-dashboard Hubitat sensor lists and
  Hickory control device ids.
- `app/routes_api.py`: JSON API routes for status, charts, debug views, rooms,
  and Hickory Hubitat controls.
- `app/routes_web.py`: room-dashboard rendering and Hubitat sensor filtering.
- `app/test_data/hubitat_get_devices.json` and `etc/sample_hubitat.json`:
  checked-in Maker API fixture payloads.

## Hubitat-Side Setup

Temperature Bot does not pair Zigbee/Z-Wave devices itself. Hubitat owns device
pairing and the Maker API app decides which devices Temperature Bot can see.

For a new temperature sensor:

1. Pair the sensor with Hubitat.
2. Give the device a stable Hubitat `name`. The code uses `name` as the system
   identifier. `label` is used as a friendlier display name when available.
3. Open the Hubitat Maker API app used by Temperature Bot.
4. Add the new sensor to the devices exposed by that Maker API app.
5. Confirm the Maker API payload includes the `TemperatureMeasurement`
   capability and an `attributes.temperature` value.
6. Wait for the next minute runner, or run the runner through the Makefile.

No manual SQLite insert is required for normal temperature logging. A new
exposed temperature sensor is created in the local `devices` table on first
successful collection. Temperature Bot re-enumerates the Maker API
`/devices/all` endpoint on every Hubitat scan, so a newly authorized live device
should be picked up on the next scan. Production cron normally runs that scan
once per minute.

Room dashboards are different: the current `/kitchen` and `/hickory`
dashboards still use exact static sensor names in `app/room_config.py`. A newly
logged Hubitat sensor will appear in the database and chart/status APIs, but it
will not appear on those room dashboards until its exact Hubitat `name` is added
to the room's `RoomConfig.sensors` list. The database has `rooms` and
`devices.room_id`, plus `/api/v1/update_device_room`, but the room dashboards
do not currently use that metadata for Hubitat sensor selection.

## Configuration And Authentication

Configuration is loaded from `TEMPERATURE_BOT_CONFIG`, or from
`temperature-bot-config.yaml` in the repository root by default.

Required Hubitat configuration:

```yaml
hubitat:
  host: 10.2.3.51
  appId: 520
secrets:
  hubitat:
    access_token: REDACTED
```

The access token can also come from the environment variable
`HUBITAT_ACCESS_TOKEN`. Environment variables take precedence over YAML secrets.

The client uses Hubitat Maker API local HTTP URLs:

```text
http://{host}/apps/api/{appId}/...?...&access_token={access_token}
```

`app.paths.TIMEOUT_SECONDS` sets a two-second HTTP timeout. The access token is
sent as a query parameter because that is the Maker API contract used by this
code. Do not commit real tokens or paste live Maker API URLs into logs or docs.

`hubitat.dashboard_appId` is optional and is only used by
`hubitat.dump_dashboard()`. If absent, dashboard dumps use `hubitat.appId`.
Dashboard dumps can also take a one-off token override because Hubitat
dashboards may have separate tokens.

## Discovery And Collection

`bin/runner.py` runs every minute in production cron. The default run path calls:

1. `update_from_ae200(conn)`
2. `update_from_hubitat(conn)`
3. `update_from_airthings(conn)`
4. the rules engine, if the master rules switch is enabled

`update_from_hubitat()` calls `hubitat.get_all_devices()` on every Hubitat scan,
which fetches the full authorized Maker API device list:

```text
GET /apps/api/{appId}/devices/all?access_token={access_token}
```

When `HUBITAT_SIMULATOR` is one of `1`, `true`, `yes`, or `on`,
`get_all_devices()` returns `app/test_data/hubitat_get_devices.json` instead of
calling Hubitat.

`hubitat.extract_temperatures()` filters the Maker API result to devices with
the `TemperatureMeasurement` capability and a non-null `attributes.temperature`
value. It normalizes common numeric string attributes to numbers:

- `temperature`
- `humidity`
- `illuminance`
- `ultravioletIndex`
- `battery`

The persisted status payload keeps Hubitat identity and state:

- `name`, `label`, `room`, `id`, `type`
- `capabilities`
- full `attributes`
- top-level convenience copies of `temperature`, `humidity`, `illuminance`,
  `motion`, `battery`, `powerSource`, `ultravioletIndex`, and `tamper`

If Hubitat prepends `OFFLINE - ` to a device `name`, `get_all_devices()` strips
that prefix before downstream matching and logging.

## Database Storage

Hubitat temperature devices are stored in the shared SQLite schema:

- `devices.device_name`: Hubitat `name`, created automatically on first log.
- `devlog.device_id`: foreign key to `devices`.
- `devlog.logtime`: Unix timestamp.
- `devlog.duration`: seconds the row remains valid.
- `devlog.temp10x`: Celsius temperature multiplied by 10.
- `devlog.status_json`: JSON status payload from `extract_temperatures()`.

`db.insert_devlog_entry()` performs run-length encoding. If the new reading has
the same `temp10x` and identical `status_json` as the most recent row, the old
row's `duration` is extended instead of inserting a duplicate. One row is not
extended beyond `db.MAX_DURATION`, currently 3600 seconds.

If the temperature is unchanged but any persisted Hubitat attribute changes,
such as humidity, illuminance, battery, or motion, the `status_json` differs and
a new `devlog` row is inserted.

The `/devices` admin page edits local metadata on the `devices` row:
`display_name`, `device_type`, `rules_enabled`, and `notes`. It does not create
Hubitat devices and does not expose a sensor through Maker API.

## Retention, Compression, And Backups

There is no source-code path that deletes old `devlog` Hubitat temperature
history as part of normal cleanup. Instead, `bin/runner.py --daily` compresses
older data:

- rows roughly one to two weeks old are averaged into five-minute rows;
- an older calendar-month window is averaged into twenty-minute rows.

This keeps long-term temperature history at lower resolution. The compression
currently rewrites only `device_id`, `logtime`, `duration`, and `temp10x`.
Detailed `status_json` fields such as humidity, illuminance, battery, and
motion are not preserved in compressed rows. This is already called out as tech
debt in `doc/tech-debt.md`.

Production database backups are whole-SQLite-file backups:

- `make deploy` copies `/var/db/temperature-bot.db` to
  `/var/db/temperature-bot-backups/temperature-bot.<UTC timestamp>.db` before
  migrations.
- `make monthly-backup` copies `/var/db/temperature-bot.db` to
  `/var/db/temperature-bot.backup.<date>.db`.

The code does not archive Hubitat event history separately. A Maker API event
history URL is defined in `app/hubitat.py`, but it is not used by the runner.

## Application APIs And UI

Hubitat data reaches the app through several paths:

- `/api/v1/status`: latest local database status for all devices.
- `/api/v1/temperature`: historical temperature series from `devlog.temp10x`.
- `/api/v1/lighting`: historical illuminance series from `status_json`.
- `/api/v1/metric?metric=humidity`: arbitrary supported status metric series.
- `/api/v1/debug/hubitat_devices`: live Maker API device names and payloads.
- `/all_devices`: web debug page that compares database, Hubitat, and AE-200
  devices through debug APIs.
- `/kitchen` and `/hickory`: room dashboards that fetch live Hubitat sensor
  payloads and filter by `app/room_config.py`.

Temperature chart and lighting chart display names prefer the current Hubitat
`label` when Hubitat is reachable, then apply the shared display-name helper.
Debug views intentionally show raw system names, often as `name (label)`.

## Hubitat Control Paths

The source contains these Hubitat control helpers:

- `hubitat.send_device_command(device_id, command, secondary_value="")`
- `hubitat.set_dimmer_level(device_id, level)`
- `hubitat.set_switch(device_id, state)`
- `hubitat.control_hickory_tv(direction)`

They use Maker API command URLs:

```text
GET /apps/api/{appId}/devices/{device_id}/{command}/{secondary_value}?access_token={access_token}
```

Current app routes expose Hickory-specific controls:

- `POST /api/v1/hickory/dimmer` with integer `level` from 0 to 100.
- `POST /api/v1/hickory/wall_light` with `light` of `inner` or `outer`, and
  `state` of `on` or `off`.
- `POST /api/v1/hickory/tv` with `direction` of `up` or `down`.
- `GET /api/v1/hickory/room_status` for current control states.

The Hickory dimmer and wall-light device ids are hard-coded in
`app/room_config.py`. The TV lift is found by Hubitat label: `TV Up` or
`TV Down`; the helper sends `on` to that component switch.

Simulator mode only simulates `get_all_devices()`. Command helpers still build
Maker API command URLs and are not safe to assume simulated.

## Defined Maker API URLs

`app/hubitat.py` defines URL templates for:

- all devices with full details;
- one device;
- one device event history;
- one device commands;
- one device capabilities;
- one device attribute;
- Maker API `postURL`;
- dashboard list;
- dashboard dump;
- device command execution.

The runner currently uses only the all-devices URL for collection. The web/API
control code uses all-devices reads and command execution. The dashboard dump
and per-device helper functions are available for diagnostics and future work.

## Tests And Local Development

Run tests and local commands through the Makefile.

- `make local-dev` runs Flask with `HUBITAT_SIMULATOR=1`.
- Pytest sets `HUBITAT_SIMULATOR=1` in `pyproject.toml`.
- `tests/test_hubitat.py` covers numeric extraction, simulator fixture loading,
  and persistence of Hubitat `status_json`.
- Route tests cover room-dashboard sensor filtering and Hickory control error
  handling. Those command tests patch Hubitat calls because command execution
  would otherwise require live hardware.

Useful live diagnostics:

```bash
make every-minute
```

```bash
poetry run python -m app.hubitat --list-devices
```

```bash
poetry run python -m app.hubitat --list-temperatures
```

The app also exposes `/all_devices` and `/api/v1/debug/hubitat_devices` for
interactive inspection.

## Short Answer: Are New Sensors Automatic?

New Hubitat temperature sensors are automatically logged only after they are
paired in Hubitat and exposed through the configured Maker API app. Once Maker
API returns the device with `TemperatureMeasurement` and a temperature value,
Temperature Bot creates the `devices` row and starts writing `devlog` rows.
Because the runner enumerates `/devices/all` every scan, no Temperature Bot
restart or local database edit is needed for normal logging.

They are not automatically added to the current room-dashboard sensor tiles.
Add the exact Hubitat `name` to `app/room_config.py` for the relevant room until
the room dashboards are changed to use `devices.room_id` or another metadata
driven assignment path.
