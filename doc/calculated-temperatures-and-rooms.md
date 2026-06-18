# Calculated Temperatures, Rooms, and Map Metadata

## Purpose

Each FCU has two temperature values:

- **FCU Temp** is the raw inlet/device temperature stored in `devlog.temp10x`.
- **Temp** is the calculated room temperature used by display, reporting, and
  automation.
- **Set Range** is the persisted allowed temperature band for an FCU. The
  system-wide minimum width is 3.0 °C; individual FCUs can use a wider range.

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

For the current `/api/v1/status` display payload, the room temperature falls
back to the raw FCU temperature when the weighted calculation has no usable
source and the FCU's own source multiplier has not been explicitly set to `0`.
Historical calculated series and the calculation helper still exclude stale
rows.

## Database

Schema changes belong in Flyway migrations under `etc/flyway/sql/`; after adding
a migration, regenerate `etc/schema.sql` with `make schema`.

Rooms are stored in `rooms`:

```sql
CREATE TABLE rooms (
    room_id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_name TEXT NOT NULL UNIQUE,
    map_json TEXT NOT NULL DEFAULT '{}'
);
```

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

FCU set range endpoint:

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
