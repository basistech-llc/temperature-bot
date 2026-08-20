# Hubitat Information

This document describes how Temperature Bot talks to Hubitat, what must be set
up on the Hubitat side, how sensors are discovered, and how Hubitat readings
are stored.

If you do not already know what a Hubitat hub or a Maker API app is, read
`doc/hardware-landscape.md` first. It also documents the two-hub topology: this
document describes hub `10.2.3.51` and Maker API app `520`, which is the only
Hubitat installation Temperature Bot can reach.

## Source Map

- `app/hubitat.py`: Hubitat Maker API client, simulator support, and device
  control helpers.
- `bin/runner.py`: minute runner that polls Hubitat and writes readings.
- `app/db.py`: device creation, current status, time-series queries, and log
  compression.
- `app/room_config.py`: room-dashboard membership and actuator configuration.
  Sensor membership is canonical; the actuator devices are configured here.
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

Room dashboards select sensors canonically: `_canonical_room_sensors()` reads
`devices.room_id`, so a newly logged Hubitat sensor appears on a room dashboard
as soon as it is assigned to that room. Assign it by dragging its row in the
main-page Air Quality matrix, or through `/api/v1/update_device_room`. No code
or configuration change is required, and no sensor names are listed in
`app/room_config.py`.

Actuators are the exception. Which switches, dimmers, and lifts a dashboard
offers is deliberate presentation configuration, so it stays in
`app/room_config.py` rather than being derived from room membership.

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

Before temperature filtering, the runner classifies and creates every authorized
Maker API device. `FanControl` devices become `FAN`; devices with actuator,
switch, level, button, door, or lock capabilities become `CONTROL`; measurement
devices become `SENSOR`. Existing non-null types are preserved.

`hubitat.extract_temperatures()` then filters the Maker API result to devices with
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

The `/devices` admin page edits `display_name`, `rules_enabled`, and `notes`.
It displays the automatically assigned `device_type` read-only. It does not
create Hubitat devices or expose a sensor through Maker API.

`make DEVICE_TYPE_DB=<path> device-type-backfill` previews classifications for
untyped historical rows. Add `APPLY=1` to persist them; the target first copies
the database to `DEVICE_TYPE_BACKUP`. Live capabilities are preferred. A narrow
name-marker fallback handles rows created before Hubitat metadata was retained.

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
- `/kitchen`, `/hickory`, `/broadway`, and `/room/<room_id>`: room dashboards
  whose sensor tiles come from canonical `devices.room_id` membership and whose
  actuator tiles come from `app/room_config.py`.

Temperature chart and lighting chart display names prefer the current Hubitat
`label` when Hubitat is reachable, then apply the shared display-name helper.
Debug views intentionally show raw system names, often as `name (label)`.

## Hubitat Control Paths

The source contains these Hubitat control helpers:

- `hubitat.send_device_command(device_id, command, secondary_value="")`
- `hubitat.set_dimmer_level(device_id, level)`
- `hubitat.set_switch(device_id, state)`
- `hubitat.set_fan_speed(device_id, speed)`
- `hubitat.control_hickory_tv(direction)`

They use Maker API command URLs:

```text
GET /apps/api/{appId}/devices/{device_id}/{command}/{secondary_value}?access_token={access_token}
```

Current app routes expose configured room controls. Each body addresses one
control by the `key` given to it in `app/room_config.py`:

- `POST /api/v1/room/<room_key>/switch` with `control` and `state` of `on` or
  `off`.
- `POST /api/v1/room/<room_key>/dimmer` with integer `level` from 0 to 100, and
  `control` when the room has more than one dimmer.
- `POST /api/v1/room/<room_key>/fan` with `control` and `speed` of `off`, `low`,
  `medium`, or `high`.
- `POST /api/v1/room/<room_key>/tv` with `direction` of `up` or `down`.
- `GET /api/v1/room/<room_key>/room_status` returns `{"controls": [...]}`, one
  entry per readable control. Each carries `key` and `kind`, plus whichever of
  `switch`, `level` (dimmers), and `speed` (fans) the device actually reported.
  A TV lift is momentary and reports no state, so it never appears; a control
  whose device could not be read is omitted rather than guessed at; and an
  attribute the device omitted is absent rather than defaulted, so a running fan
  that reports no `switch` is never published as off.

A control key the room does not configure is a 404, the same answer an unknown
room gets.

Device ids and TV component labels are configured per room in
`app/room_config.py`. The helper sends `on` to the selected TV component
switch.

`/api/v1/room/<room_key>/wall_light` is an alias of `/switch` that spells the
control key `light`, and the `/api/v1/hickory/...` paths remain compatibility
aliases. Each alias is registered under its own Flask endpoint name; sharing one
endpoint made Werkzeug 308-redirect the generic URL to the Hickory-specific one.

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
control code uses per-device reads for room control status and the all-devices
read elsewhere, plus command execution. The dashboard dump and the remaining
per-device helpers are available for diagnostics and future work.

### The two attribute shapes

The two read endpoints disagree about `attributes`, and the difference is easy
to miss because both are valid JSON describing the same device:

```text
GET /devices/all       "attributes": {"switch": "on", "level": "70", ...}
GET /devices/<id>      "attributes": [{"name": "switch", "currentValue": "on",
                                       "dataType": "ENUM"}, ...]
```

`HubitatControlDevice` accepts both and normalizes the list into the mapping.
Before it did, every room control status read failed model validation, so the
Hickory tiles reported their controls unreadable in production and each failure
logged a large warning.

Two quirks the captured fixtures in `app/test_data/hubitat_control_devices.json`
pin down:

- A `FanControl` device publishes a wider speed vocabulary than the four speeds
  we command — `low`, `medium-low`, `medium`, `medium-high`, `high`, `on`,
  `off`, `auto`. This is why the speed we report is an untyped string.
- The `hueBridgeGroup` driver lists `switch` and `colorName` twice. The last
  entry wins; both carried the same value when observed.

Attributes a device does not report are absent, not defaulted. A fan with no
`switch` attribute must not be published as off.

### Hub endpoints outside Maker API

Maker API only ever describes the devices it has been told to expose. To see
what the hub itself knows, including Hub Mesh devices shared from another hub,
read the hub UI's own JSON. These need no access token and are read-only:

```text
GET http://10.2.3.51/hub2/devicesList     every device, with source Linked/System/User
GET http://10.2.3.51/apps/api/520/rooms   Hubitat's own rooms, which we do not use
```

The first is the right tool for "is this device on the hub at all", a question
the Maker API device list cannot answer.

## Tests And Local Development

Run tests and local commands through the Makefile.

- `make local-dev` runs Flask with `HUBITAT_SIMULATOR=1`.
- Pytest sets `HUBITAT_SIMULATOR=1` in `pyproject.toml`.
- `tests/test_hubitat.py` covers numeric extraction, simulator fixture loading,
  and persistence of Hubitat `status_json`.
- Route tests cover room-dashboard sensor filtering and Hickory control error
  handling. Those command tests patch Hubitat calls because command execution
  would otherwise require live hardware. An autouse fixture in
  `tests/conftest.py` now enforces that: it replaces `send_device_command`, the
  one function every Hubitat write goes through, with a refusal, so a test that
  forgets to patch fails instead of switching an office outlet.

Useful live diagnostics:

```bash
make every-minute
```

```bash
poetry run python -m app.hubitat --list-temperatures
```

`--list-devices` is an alias for the same output despite its name: both filter
Maker API's response to devices reporting a temperature. Neither can show a
switch, outlet, or fan. To see everything Maker API exposes, query it directly
-- see `doc/hardware-landscape.md`.

The app also exposes `/all_devices` and `/api/v1/debug/hubitat_devices` for
interactive inspection.

## Short Answer: Are New Sensors Automatic?

New Hubitat temperature sensors are automatically logged only after they are
paired in Hubitat and exposed through the configured Maker API app. Once Maker
API returns the device with `TemperatureMeasurement` and a temperature value,
Temperature Bot creates the `devices` row and starts writing `devlog` rows.
Because the runner enumerates `/devices/all` every scan, no Temperature Bot
restart or local database edit is needed for normal logging.

They do not appear on a room dashboard until they are assigned to a room, because
dashboard sensor tiles come from `devices.room_id`. A new sensor starts
Unassigned; drag it onto a room in the main-page Air Quality matrix, and it
appears on that room's dashboard immediately. No code change is involved.
