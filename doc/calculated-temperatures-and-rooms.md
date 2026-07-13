# Calculated Temperatures, Rooms, and Map Metadata

## Purpose

Each FCU has two temperature values:

- **FCU Temp** is the raw inlet/device temperature stored in `devlog.temp10x`.
- **Room Temp** is the calculated room temperature used by display, reporting,
  and automation.
- **Rule Set Range** is the persisted allowed temperature band for an FCU. The
  system-wide minimum width is 3.0 °C; individual FCUs can use a wider range.
  This range is local to TemperatureBot rules; in Auto mode, the FCU Set Temp
  column edits the AE-200 Heat/Cool setpoints instead.
  The FCU Set Temp and Rule Set Range slider tracks use a common 55 °F to 85 °F
  visual scale.

Calculated temperature is a weighted average of the FCU's own raw temperature
and any configured temperature-reporting devices:

```text
calculated_temp =
  sum(valid_source_temp * source_multiplier) / sum(source_multiplier)
```

The FCU's own temperature defaults to weight `1.0`; every other
temperature-reporting device defaults to weight `0.0`. Persisted rows in
`fcu_temp_sources` override those defaults. A multiplier of `0` means the
source is not used, including when the FCU's own weight is explicitly set to
`0`.

Use `db.get_fcu_temp_source_weights()` whenever code needs source weights. It is
the single place that applies the hard-coded defaults, so display and
calculation stay consistent.

Temperature sources older than `TEMP_SOURCE_STALE_SECONDS` are excluded from the
calculation. The constant is defined once in `app/constants.py` and is currently
10 minutes. The FCU temperature popup must tell users that readings older than
10 minutes are ignored.

`app/room_metrics.py` is the shared source-selection boundary for current room
temperature and humidity. `db.fetch_latest_room_metric_snapshots()` performs
the raw SQLite lookup and returns typed snapshots; `select_room_metric_sources()`
then applies room membership, excludes ERV and `INTERNAL` devices, calculates
age from `logtime + duration`, rejects stale readings, and extracts the chosen
metric. Temperature is normalized to Celsius and humidity supports both
Hubitat scalar/`attributes` payloads and Airthings `{value, unit}` payloads.
Missing or malformed metrics are returned as explicit exclusion outcomes.

The selector accepts an explicit evaluation time and does not read Flask
request state. This keeps route and calculation callers on one deterministic
mechanism and allows historical callers to use the same freshness boundary.

For the current `/api/v1/status` display payload, the room temperature falls
back to the raw FCU temperature when the weighted calculation has no usable
source and the FCU's own source multiplier has not been explicitly set to `0`.
Historical calculated series and the calculation helper still exclude stale
rows.

The dashboard charts these values separately: clicking **FCU Temp** opens the
raw temperature chart (`mode=raw`), while clicking **Room Temp** opens the
calculated room-temperature chart (`mode=calculated`). The calculated series is
not stored as separate measurement rows; it is computed from historical raw
source readings and the persisted `fcu_temp_sources` multipliers.

## Database

Schema changes belong in Flyway migrations under `etc/flyway/sql/`; after adding
a migration, regenerate `etc/schema.sql` with `make schema`.

Rooms are stored in `rooms`:

```sql
CREATE TABLE rooms (
    room_id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_name TEXT NOT NULL UNIQUE,
    map_json TEXT NOT NULL DEFAULT '{}',
    fcu_device_id INTEGER REFERENCES devices(device_id)
);
```

Every FCU owns exactly one room and is assigned to that room. FCU discovery
creates both records in one transaction. The default room name is the FCU
display name, falling back to its device name; collisions use `Name (2)`,
`Name (3)`, and so on. Migration V9 claims compatible legacy assignments,
creates missing FCU rooms, and clears non-FCU assignments so physical sensors
start in the virtual **Unassigned** group. ERVs and internal pseudo-devices are
also left unassigned.

Unique partial indexes on `rooms.fcu_device_id` and FCU `devices.room_id`
prevent an FCU from owning several rooms or several FCUs from sharing a room.
`db.reconcile_fcu_rooms()` provides an idempotent repair path for persisted FCU
topology.

`rooms.map_json` is JSON validated by the Pydantic `RoomMap` model:

```json
{
  "polygon": [{"x": 120, "y": 80}, {"x": 220, "y": 80}, {"x": 230, "y": 160}],
  "color": "#4f9d69"
}
```

Devices can be assigned to rooms:

```sql
ALTER TABLE devices ADD COLUMN room_id INTEGER REFERENCES rooms(room_id);
```

FCU temperature source weights are stored in `fcu_temp_sources`:

```sql
CREATE TABLE fcu_temp_sources (
    fcu_device_id INTEGER NOT NULL,
    source_device_id INTEGER NOT NULL,
    multiplier REAL NOT NULL CHECK (multiplier >= 0),
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (fcu_device_id, source_device_id)
);
```

All temperature-reporting devices are eligible sources, not only `aqi_mon`
devices. Eligibility is determined by having a latest `devlog.temp10x` reading.

FCU set ranges are stored in `fcu_set_ranges`:

```sql
CREATE TABLE fcu_set_ranges (
    fcu_device_id INTEGER PRIMARY KEY,
    set_range_low_c REAL NOT NULL,
    set_range_high_c REAL NOT NULL,
    updated_at INTEGER NOT NULL,
    CHECK (set_range_high_c >= set_range_low_c + 3.0)
);
```

When no row exists yet, the effective default range is centered on the AE-200
`SetTemp` value and uses the 3.0 °C minimum width. If `SetTemp` is unavailable,
the default center is 21.0 °C. Saving a range persists the low/high Celsius
endpoints for that FCU.

## API

`GET /api/v1/status` includes room and calculated-temperature fields where
available:

```json
{
  "device_id": 12,
  "room_id": 203,
  "room_name": "Hickory",
  "temp10x": 224,
  "calculated_temp10x": 231,
  "temp_source_stale_seconds": 600,
  "set_range_low_c": 20.0,
  "set_range_high_c": 23.5,
  "min_set_range_c": 3.0
}
```

Room endpoints:

- `GET /api/v1/rooms`
- `POST /api/v1/rooms`
- `GET /api/v1/rooms/<room_id>`
- `PATCH /api/v1/rooms/<room_id>`

Room endpoints use one Pydantic `Room` object for create, update, and response
payloads. `room_name` is required when creating a room. `room_id` is omitted
when creating a new room. Other `None` fields are not serialized into JSON, and
updates write only fields that are set. Room payloads use `map` at the API
boundary and `map_json` in SQLite:

```json
{
  "room_name": "Hickory",
  "map": {
    "polygon": [{"x": 120, "y": 80}, {"x": 220, "y": 80}],
    "color": "#4f9d69"
  }
}
```

Device-room assignment:

```http
POST /api/v1/update_device_room
```

```json
{
  "device_id": 12,
  "room_id": 203
}
```

FCU temperature source endpoints:

- `GET /api/v1/fcu_temp_sources?fcu_device_id=12`
- `POST /api/v1/fcu_temp_source`

`GET /api/v1/fcu_temp_sources` returns every temperature-reporting device,
including the FCU itself:

```json
{
  "fcu_device_id": 12,
  "stale_seconds": 600,
  "sources": [
    {
      "source_device_id": 12,
      "device_name": "Hickory FCU",
      "room_id": 203,
      "is_fcu_self": true,
      "temp10x": 224,
      "age_seconds": 90,
      "is_stale": false,
      "multiplier": 1.0,
      "included": true
    }
  ]
}
```

`POST /api/v1/fcu_temp_source` persists one multiplier, or an array of
multipliers for one FCU. Array requests are atomic: if any row fails validation
or references an unknown device, none of the rows are saved.

```json
{
  "fcu_device_id": 12,
  "source_device_id": 34,
  "multiplier": 0.75
}
```

```json
[
  {
    "fcu_device_id": 12,
    "source_device_id": 34,
    "multiplier": 0.75
  },
  {
    "fcu_device_id": 12,
    "source_device_id": 56,
    "multiplier": 1.25
  }
]
```

The main dashboard's temperature-source popup keeps multiplier edits local until
the user clicks **Save**. **Revert** restores the loaded values, **Cancel**
closes without saving, and stale sources are shown after current sources.

Changes are written to `changelog` with old and new multiplier values. The log
API includes `current_values` and `new_value` so old/new values are visible.

Temperature chart endpoints:

- `GET /api/v1/temperature?mode=raw&device_ids=12` returns stored raw
  `devlog.temp10x` readings.
- `GET /api/v1/temperature?mode=calculated&device_ids=12` returns calculated FCU
  room-temperature history for FCU devices only.

FCU Auto Heat/Cool setpoint endpoint:

- `POST /api/v1/set_auto_temp`

```json
{
  "device_id": 12,
  "heat_set_temp_c": 20.0,
  "cool_set_temp_c": 25.0
}
```

The endpoint writes AE-200 `SetTemp2` for Heat and `SetTemp1` for Cool, records
the change in `changelog`, and stores the read-back status in `devlog`.
After an operator edits a single setpoint or range, the UI colors the requested
number blue while waiting for status read-back. For 30 seconds, stale read-back
values that do not match the request are suppressed; after that, a mismatching
read-back value is shown in red.

FCU Rule Set Range endpoint:

- `POST /api/v1/set_range`

```json
{
  "device_id": 12,
  "set_range_low_c": 20.0,
  "set_range_high_c": 23.5
}
```

The endpoint rejects ranges narrower than 3.0 °C, persists accepted ranges in
`fcu_set_ranges`, and writes old/new effective values to `changelog`.

Temperature chart modes:

- `GET /api/v1/temperature?mode=raw` returns raw readings for all temperature
  devices.
- `GET /api/v1/temperature?mode=calculated` returns only FCUs and their
  calculated temperature series.

Historical calculated series use the current source multipliers. If exact
historical reconstruction after multiplier changes becomes required, add a
versioned multiplier history table before changing the chart semantics.

## Rules

Rules should use `get_temp(device_id)` for effective temperature. It returns the
calculated FCU temperature when available, otherwise the raw `temp10x` value.

Use `get_fcu_temp(device_id)` only when a rule specifically needs the raw FCU
inlet/device temperature.
