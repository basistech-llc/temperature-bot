# Hardware Landscape

An orientation for anyone who works on Temperature Bot without having stood in
the building. It explains what the physical equipment is, who talks to whom, and
why a device you can plainly see somewhere else may be invisible to this
application.

Every other hardware document here answers "how does our code call X". This one
answers "what is X, and why is it in the picture at all". Read this first, then:

- `doc/Hubitat_Info.md` for the Hubitat Maker API mechanics.
- `doc/AE200-TemperatureBot.md` for AE-200 operation modes.
- `doc/airthings.md` for the Airthings API.
- `doc/calculated-temperatures-and-rooms.md` for how readings become room
  temperatures.

## The Shape Of The System

Temperature Bot owns no hardware. It is a reader and a remote control for four
independent systems that were installed for their own reasons:

```text
  Zigbee / Z-Wave sensors  ──radio──>  Hubitat hub  ──HTTP──┐
  Zigbee / Z-Wave switches ──radio──>  (Maker API)          │
                                                            │
  Mitsubishi fan coils + ERVs ──building LAN──> AE-200 ─────┼──> Temperature Bot
                                                            │      (bin/runner.py,
  Airthings air-quality monitors ──> Airthings cloud ───────┤       once a minute)
                                                            │           │
  Outdoor air quality ──> AQICN / AirNow / Google ──────────┘           v
                                                                     SQLite
                                                                        │
                                                                        v
                                                                  Flask web UI
```

`bin/runner.py` runs from cron every minute, polls each system, and writes rows
into one SQLite database. The web UI reads that database. Nothing streams; every
number you see on a page was pulled by a poll.

## Hubitat

### What the hardware is

A **Hubitat Elevation hub** is a small always-on box on the office LAN. It is a
home-automation controller: battery- and mains-powered sensors and switches
around the building speak short-range radio protocols (**Z-Wave** and
**Zigbee** — low-power mesh radios, not WiFi), and the hub is the one device
that speaks those radios and bridges them to the network. Nothing else in our
stack can hear a Z-Wave sensor directly.

The sensors are mostly **Aeotec MultiSensor 6** units: one small puck that
reports temperature, humidity, illuminance, motion, tamper, and battery. The
switches are a mix of in-wall relays and smart plugs (GE Enbrighten, Zooz,
Minoston) plus a Hue bridge group for dimmable lights.

**Pairing** — joining a device to the hub's radio mesh — happens on the hub, by
a person standing next to the device. Temperature Bot never pairs anything.

### Apps, and why they matter more than you would expect

A Hubitat hub runs **apps**. Two kinds matter to us, and confusing them is the
single most common source of "why can't the bot see this device":

- A **Maker API app** is a programmable allowlist. You install it, tick a set of
  devices, and it issues an app id and an access token. It then exposes *only
  the ticked devices* over plain HTTP. This is our entire interface to Hubitat —
  everything we read and every command we send goes through one Maker API app.
- A **Dashboard app** is a display page for humans: a grid of tiles at a URL you
  can open on a wall tablet. It has its own app id and its own token, and its
  own separate list of devices.

These lists are unrelated. **A device shown on a Hubitat dashboard is not
thereby visible to Temperature Bot.** If it is not ticked in our Maker API app,
it does not exist as far as this code is concerned — no reading, no command, no
`devices` row, no error message pointing at the cause.

### There are two hubs

This is the part that most often surprises people, including agents reading the
code:

| Hub | Used for | App | Notes |
| --- | --- | --- | --- |
| `10.2.3.51` | **Everything Temperature Bot does** | Maker API, app `520` | Configured in `temperature-bot-config.yaml`. Authorizes 21 devices. |
| `10.2.3.52` | Hubitat's own wall dashboards | Dashboard, app `449` ("Broadway Controls") and others | We do not talk to this hub at all. |

`temperature-bot-config.yaml` has exactly one `hubitat.host` and one
`hubitat.appId`. **The code cannot reach a second hub.** Supporting one would be
a change to the configuration model, not just an extra token.

**Hub Mesh** is a Hubitat feature that mirrors a device from one hub onto
another so both can use it. Some of our sensors are meshed this way, and the
mirrored copy **gets a different device id on each hub**. The same physical
sensor in the Broadway space is:

- id `37` on hub `.52`, labelled `Broadway Sensor Center`
- id `525` on hub `.51`, labelled `Broadway Center`

So a device id copied from a Hubitat dashboard URL or layout is meaningless to
us unless that device is also meshed to `.51` and ticked in Maker API app 520.

### Practical consequence

When someone says "add the X control to a Temperature Bot page", the first
question is not a code question. It is: *is X exposed by Maker API app 520 on
hub `.51`?* Check with:

```bash
poetry run python -m app.hubitat --list-devices
```

If it is not in that list, the work is blocked on a hub-side change by someone
on site — mesh the device to `.51` if needed, then tick it in the Maker API app.
No amount of application code substitutes for that.

## The AE-200

### What the hardware is

The **Mitsubishi AE-200** is a central controller for the building's
air conditioning. It is a wall-mounted unit wired to the HVAC equipment on
Mitsubishi's own control bus, and it presents that equipment to the LAN. Ours is
at `10.2.1.20`.

Two kinds of equipment hang off it, and the distinction runs through the whole
codebase:

- An **FCU** (fan coil unit) is an air conditioner for one space: a coil with
  hot or cold water or refrigerant, and a fan blowing room air across it. It
  heats and cools. It has a mode (Cool/Heat/Fan/Dry/Auto), a fan speed, a
  setpoint, and it reports an inlet air temperature. This is what people mean by
  "the AC in the Bamboo room".
- An **ERV** (energy recovery ventilator) does *not* heat or cool. It exchanges
  stale indoor air for fresh outdoor air, passing the two streams alongside each
  other so the outgoing air pre-conditions the incoming air. It has a fan speed
  and nothing else. It is a ventilation device.

In the UI, FCUs get the full card with a setpoint; ERVs get a speed row only.

### How we talk to it

Over a **WebSocket** at `ws://10.2.1.20/b_xmlproc/`, exchanging XML. This is not
a documented public API; the client in `app/ae200.py` originated from the
`natevoci/ae200` reverse-engineering project.

The connection is slow and intolerant of concurrency, which shapes a surprising
amount of the code: commands are serialized across processes with a file lock,
timings are recorded (`doc/performance-monitoring.md`), and `AE200_SIMULATOR=1`
swaps in canned payloads from `app/test_data/` so development does not touch the
real hardware.

`pyproject.toml` declares `pymodbus`, but no module imports it. There is no live
Modbus path today, despite what older notes may say.

## Airthings

**Airthings** monitors are consumer air-quality devices — radon, CO2, VOC,
particulates, plus temperature and humidity. Unlike everything else here they
are **cloud-only**: the device talks to Airthings' servers, and we read the
readings back out of `consumer-api.airthings.com` with OAuth client credentials.
There is no local path, so this integration depends on the office internet
connection and on Airthings' service being up.

## Outdoor Air Quality

Not hardware at all. `app/airquality.py` fetches the outdoor AQI for the area
from public services — **AQICN**, **AirNow** (the US EPA's feed, keyed by zip
code), and Google's air-quality API. This is what the rules engine consults
before deciding whether opening up ventilation is a good idea.

## How A Physical Device Becomes A Row

Every source above converges on the `devices` table, one row per thing, and the
`devlog` table, which is the time series. `bin/runner.py` creates a `devices`
row automatically the first time a source reports a device it has not seen.

Each row carries a `device_type`, assigned from the device's capabilities:

| `device_type` | Meaning |
| --- | --- |
| `FCU` | An AE-200 fan coil unit. |
| `ERV` | An AE-200 ventilator. |
| `SENSOR` | Anything that measures — Hubitat sensors, Airthings monitors. |
| `CONTROL` | A Hubitat actuator: switch, dimmer, relay, button. |
| `INTERNAL` | Not hardware. Pseudo-devices such as `rules_engine`. |

Temperatures are stored as `temp10x` — degrees Celsius times ten, as an integer.
Consecutive identical readings are run-length encoded into one row with a longer
`duration` rather than repeated.

## Rooms

A **room** is our own concept, not a Hubitat or Mitsubishi one. It exists so the
UI can say "the Bamboo room is 23°" rather than naming a sensor.

The rules, from `doc/rooms-implementation-plan.md`:

- Every FCU owns exactly one room, created automatically when the FCU is
  discovered. This is why there is a "Broadway North" room and a "Broadway
  South" room and no single "Broadway" room — there are two fan coil units
  serving that space.
- Rooms can also exist without an FCU (Garage, Data Closet).
- Every other physical device can be assigned to a room. ERVs and `INTERNAL`
  pseudo-devices cannot.
- `room_id IS NULL` means Unassigned, which is a display grouping, not a row.
- A room's `room_id` is its stable identity; `room_name` is a display label and
  can be renamed.

Assignments are made by dragging rows in the Air Quality matrix on the main
page. A room's temperature is a weighted average of the fresh readings from its
assigned sensors; its humidity is an equal-weight mean. Readings older than ten
minutes are excluded rather than shown stale.

## Simulators

None of the above is needed to develop locally. `make local-dev` runs with
simulator flags set, serving canned payloads:

| Flag | Replaces |
| --- | --- |
| `HUBITAT_SIMULATOR=1` | Maker API device list |
| `AE200_SIMULATOR=1` | AE-200 WebSocket |
| `AIRTHINGS_SIMULATOR=1` | Airthings cloud |
| `AQICN_SIMULATOR=1` | Outdoor AQI |

One caveat worth knowing: the Hubitat simulator only simulates *reading*.
Command helpers still build real Maker API URLs, so a code path that sends a
switch command is not automatically safe just because the simulator is on.

## Troubleshooting Map

| Symptom | Likely cause |
| --- | --- |
| A device appears on a Hubitat dashboard but not in our UI | Not ticked in Maker API app 520, or only exists on hub `.52`. |
| A device id from a Hubitat URL does not work in our config | Ids are per-hub. Hub Mesh gives the same sensor a different id on each hub. |
| A room dashboard tile says "No data for 2h" | Its last reading is older than the ten-minute freshness cutoff. Says nothing about the device itself — the runner, cron, or the hub may be what stopped. |
| A control tile says "Unavailable" | Different condition: the live Maker API read for that device just failed, so it is not exposed on hub `.51` or the hub is unreachable. |
| A sensor logs data but appears on no room page | It has no `room_id`. Assign it in the Air Quality matrix. |
| AE-200 values are stale or commands are slow | The WebSocket is serialized and slow by nature; see `doc/performance-monitoring.md`. |
| Airthings values stop updating | Cloud-only integration — check internet and Airthings service. |
