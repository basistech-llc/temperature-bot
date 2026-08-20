# Site Manual

A census of the Hubitat installation: which hubs exist, what is paired to each,
which apps run on them, and exactly which devices Temperature Bot can see.

`doc/hardware-landscape.md` is the companion to this file and should be read
first. It explains the *concepts* — what a Hubitat hub is, what Z-Wave and
Zigbee are, the difference between pairing, Hub Mesh, and Maker API exposure,
and why a device on a wall dashboard may be invisible to us. This file explains
*what is actually installed*, and deliberately does not repeat the concepts.

**This is a snapshot, taken 2026-08-20.** Devices get added, renamed, and
re-meshed without anyone updating a document. Treat the tables here as a
starting map, not as truth; "Re-running This Survey" at the end gives the
read-only commands that regenerate every number on this page in about a minute.

## The Four Hubs

There are four Hubitat hubs on the office LAN, not two. All four are the same
model on the same firmware, all four answer HTTP on the LAN with no
authentication, and all four report their radios healthy.

| Host | Hub name | Devices | Top-level apps | What it is for |
| --- | --- | --- | --- | --- |
| `10.2.3.51` | Somerville Area 51 | 120 (83 native, 37 meshed in) | 12 | The hub Temperature Bot talks to. Area 51, Hickory, Dungeon, Huddle and Meeting rooms, plus everything meshed in from `.52` and `.53`. |
| `10.2.3.52` | Somerville Broadway | 40 | 8 | Broadway, Lobby, Kitchen, Outside. Offers 33 devices to the mesh; 29 are linked onto `.51`. |
| `10.2.3.53` | Somerville Greenhouse | 11 | 5 | The Greenhouse and the Lobby color/intensity dimmers. Offers 8 devices; all 8 are linked onto `.51`. |
| `10.2.3.54` | CALA Garage | 15 | 4 | Garage parking-spot sensors and heaters. Shares nothing, runs no Maker API, and is invisible to every other hub and to us. |

Common to all four, as of the survey:

- Model **C-8 Pro**, platform **2.5.0.159**, with **2.5.1.152** available. Nobody
  should apply that update casually: `.51` is what feeds every reading we store.
- Temperature scale **C**, matching our `temp10x` storage.
- No `zwaveOffline`, `zigbeeOffline`, load, or memory alerts on any hub.

The app column counts **top-level app instances only**, the same way the device
column would mislead if it stopped at the top level. Rule Machine is one
instance holding ten rules; a Dashboards instance holds five dashboards. Counting
every nested child the totals are 44, 32, 15, and 5.

One trap in the JSON: `baseModel.zigbeeStatus` and `baseModel.zwaveStatus` read
`"false"` on all four hubs and this does **not** mean the radios are off — `.51`
has 39 Z-Wave devices, most of which had reported within the hour the survey ran.
Those fields describe a UI state. For radio health read `alerts.zwaveOffline` and `alerts.zigbeeOffline`.

## What Temperature Bot Can Actually See

Everything we read and every command we send goes through **one** Maker API app:
app `520`, "Maker API for Temperature Bot", on `10.2.3.51`. It exposes **31
devices**. That is the entire hardware surface of this application. The four
hubs hold 186 device rows between them, 37 of which are mesh duplicates, so 149
distinct devices exist in the building and 118 of them may as well not, as far
as our code is concerned.

| `.51` id | Label Maker API reports | Device type | Where it comes from |
| --- | --- | --- | --- |
| `98` | Dungeon Cage | AeotecMultiSensor6 | native to `.51` |
| `129` | A51-1 | AeotecMultiSensor6 | native to `.51` |
| `130` | A51-2 | AeotecMultiSensor6 | native to `.51` |
| `134` | A51-3 | AeotecMultiSensor6 | native to `.51` |
| `135` | A51-4 | AeotecMultiSensor6 | native to `.51` |
| `260` | Broadway Pendant Lights | GE Enbrighten Z-Wave Smart Switch | meshed from `10.2.3.52` id `291` |
| `354` | Sidewalk Washer North | GE Enbrighten Z-Wave Smart Switch | meshed from `10.2.3.52` id `294` |
| `355` | Sidewalk Washer South | GE Enbrighten Z-Wave Smart Switch | meshed from `10.2.3.52` id `295` |
| `356` | Whiteboard Washer | GE Enbrighten Z-Wave Smart Switch | meshed from `10.2.3.52` id `293` |
| `359` | Data Closet Fan | GE Smart Fan Control | meshed from `10.2.3.52` id `137` |
| `360` | Garage Washer North | GE Enbrighten Z-Wave Smart Switch | meshed from `10.2.3.52` id `136` |
| `361` | Garage Washer South | GE Enbrighten Z-Wave Smart Switch | meshed from `10.2.3.52` id `297` |
| `454` | Green Wall - Inner | GE Enbrighten Z-Wave Smart Switch | native to `.51` |
| `522` | Lobby Sensor | AeotecMultiSensor6 | meshed from `10.2.3.52` id `38` |
| `523` | Greenhouse East | AeotecMultiSensor6 | meshed from `10.2.3.53` id `35` |
| `524` | Greenhouse West | AeotecMultiSensor6 | meshed from `10.2.3.53` id `34` |
| `525` | Broadway Center | AeotecMultiSensor6 | meshed from `10.2.3.52` id `37` |
| `526` | Broadway North | AeotecMultiSensor6 | meshed from `10.2.3.52` id `36` |
| `527` | Broadway South | AeotecMultiSensor6 | meshed from `10.2.3.52` id `151` |
| `528` | Data Closet Sensor | AeotecMultiSensor6 | meshed from `10.2.3.52` id `138` |
| `532` | A51 Hallway Sensor | AeotecMultiSensor6 | native to `.51` |
| `550` | Green Wall - Outer | Minoston MP31ZP Smart Plug | native to `.51` |
| `566` | Hickory Lights Remote | Aeon WallMote | native to `.51` |
| `581` | Hickory Dimmable Lights | hueBridgeGroup | native to `.51` |
| `610` | Hickory TV Up/Down Relay | Zooz ZEN17 Universal Relay Advanced | native to `.51` |
| `611` | TV Up | Generic Component Switch | child of `610` (Hickory TV Up/Down Relay) |
| `612` | TV Down | Generic Component Switch | child of `610` (Hickory TV Up/Down Relay) |
| `616` | Broadway Spot Lights | Minoston Mini Power Meter Plug | meshed from `10.2.3.52` id `393` |
| `617` | Hickory Sensor | AeotecMultiSensor6 | native to `.51` |
| `618` | Broadway TV Cart Left on Somerville Broadway | Generic Z-Wave Plus Outlet | meshed from `10.2.3.52` id `395` |
| `619` | Broadway TV Cart Right on Somerville Broadway | Generic Z-Wave Plus Outlet | meshed from `10.2.3.52` id `396` |

Three things in that table are worth stopping on.

**`611` and `612` are child devices.** The Zooz ZEN17 relay (`610`) creates two
component switches under itself, and Hubitat's device list nests them inside
their parent. A tool that reads only the top level of `/hub2/devicesList` counts
115 devices on `.51` and never sees these two — which is why this file says 120
and older notes say 115. Both numbers came from the same hub on the same day.

**`618` and `619` carry their hub name in their label.** Maker API reports them
as "Broadway TV Cart Left on Somerville Broadway". That suffix is part of the
label as meshed, not something we add. `app/room_config.py` overrides the
display name, so the UI says "TV Cart Left"; the raw label still reads the long
way in any Maker API output.

**More than half of what we read is not paired to `.51` at all.** Seventeen of
the 31 arrive by Hub Mesh from `.52` or `.53`. That is the subject of the next
section, and it is the single most common source of wrong device ids here.

## The Hub Mesh Map

Hub Mesh shares an already-paired device from one hub onto another. The
receiving hub treats it as a first-class device — but **assigns it a new id**.
The same physical sensor is `37` on `.52` and `525` on `.51`. An id copied from
another hub's dashboard or URL is at best dead on `.51` and at worst names an
unrelated device; this has already caused a real bug, when three Broadway
control ids taken from `.52` turned out on `.51` to be Kitchen Counter Lights,
Cedar Lights, and Willow Lights.

This table is the translation. Every device on `.51` that came from somewhere
else, with the id and name it has at its source.

| `.51` id | Name on `.51` | Source hub | Source id | Name on the source hub | App 520 |
| --- | --- | --- | --- | --- | --- |
| `257` | Bamboo Lights | `10.2.3.52` | `3` | Bamboo Lights | — |
| `258` | Kitchen Main Lights | `10.2.3.52` | `290` | Kitchen Main Lights | — |
| `259` | Lobby Main Lights | `10.2.3.52` | `289` | Lobby Main Lights | — |
| `260` | Broadway Pendant Lights | `10.2.3.52` | `291` | Broadway Pendant Lights | yes |
| `289` | Lobby Long Grazers | `10.2.3.52` | `66` | Lobby Long Grazers | — |
| `290` | Lobby Short Grazers | `10.2.3.52` | `65` | Lobby Short Grazers | — |
| `291` | Kitchen Counter Lights | `10.2.3.52` | `40` | Kitchen Counter Lights | — |
| `292` | Main Entrance Lights | `10.2.3.52` | `292` | Main Entrance Lights | — |
| `293` | Cedar Lights | `10.2.3.52` | `97` | Cedar Lights | — |
| `294` | Willow Lights | `10.2.3.52` | `98` | Willow Lights | — |
| `353` | Column & Sidewalk Lights | `10.2.3.52` | `296` | Column & Sidewalk Lights | — |
| `354` | Sidewalk Washer North | `10.2.3.52` | `294` | Sidewalk Washer North | yes |
| `355` | Sidewalk Washer South | `10.2.3.52` | `295` | Sidewalk Washer South | yes |
| `356` | Whiteboard Washer | `10.2.3.52` | `293` | Whiteboard Washer | yes |
| `357` | Broadway Lights | `10.2.3.52` | `132` | Broadway Lights | — |
| `358` | Lobby Lights | `10.2.3.52` | `133` | Lobby Lights | — |
| `359` | Data Closet Fan | `10.2.3.52` | `137` | Data Closet Fan | yes |
| `360` | Garage Washer North | `10.2.3.52` | `136` | Garage Washer North | yes |
| `361` | Garage Washer South | `10.2.3.52` | `297` | Garage Washer South | yes |
| `368` | Garden Lights | `10.2.3.52` | `141` | Garden Lights | — |
| `380` | Greenwall White Lights | `10.2.3.53` | `3` | Greenwall White Lights | — |
| `381` | Greenwall Yellow Lights | `10.2.3.53` | `4` | Greenwall Yellow Lights | — |
| `382` | Greenhouse Main Lights | `10.2.3.53` | `97` | Greenhouse Main Lights | — |
| `417` | Greenhouse Intensity | `10.2.3.53` | `36` | Greenhouse Intensity | — |
| `418` | Lobby Color | `10.2.3.53` | `65` | Lobby Color | — |
| `419` | Lobby Intensity | `10.2.3.53` | `66` | Lobby Intensity | — |
| `519` | Broadway Power Monitor | `10.2.3.52` | `387` | Broadway Power Monitor | — |
| `522` | Lobby Sensor | `10.2.3.52` | `38` | Lobby Sensor | yes |
| `523` | Greenhouse East | `10.2.3.53` | `35` | Greenhouse Sensor East | yes |
| `524` | Greenhouse West | `10.2.3.53` | `34` | Greenhouse Sensor West | yes |
| `525` | Broadway Center | `10.2.3.52` | `37` | Broadway Sensor Center | yes |
| `526` | Broadway North | `10.2.3.52` | `36` | Broadway Sensor North | yes |
| `527` | Broadway South | `10.2.3.52` | `151` | Broadway Sensor South | yes |
| `528` | Data Closet Sensor | `10.2.3.52` | `138` | Data Closet Sensor | yes |
| `616` | Broadway Spot Lights | `10.2.3.52` | `393` | Broadway Spot Lights | yes |
| `618` | Broadway TV Cart Left on Somerville Broadway | `10.2.3.52` | `395` | Broadway TV Cart Left | yes |
| `619` | Broadway TV Cart Right on Somerville Broadway | `10.2.3.52` | `396` | Broadway TV Cart Right | yes |

Twenty-nine of these come from `.52` and eight from `.53`. `.54` contributes
nothing. Note that `.52` *offers* thirty-three — four window shades are shared
but never linked, so they are absent from this table; see the `.52` section.

### Devices `.51` shares outward

`.51` also offers twenty of its own devices to the mesh. **Nothing currently
consumes them** — `.52`, `.53`, and `.54` have no linked devices at all, and only
another Hubitat hub can link a meshed device, so this is not how the Home
Assistant integration below reaches anything. Most likely they are leftovers
from an earlier arrangement. Either way, sharing a device out has no effect on
what Temperature Bot sees; only app `520` decides that.

| `.51` id | Name | Hub room |
| --- | --- | --- |
| `33` | Shower Room Lights | Shower Room |
| `66` | Dungeon Ceiling | Dungeon |
| `98` | Dungeon Cage | Dungeon |
| `100` | Restroom Lights | Restrooms |
| `101` | Maple Lights | Meeting Rooms |
| `129` | A51-1 | Area 51 |
| `130` | A51-2 | Area 51 |
| `131` | Banyan Lights | Meeting Rooms |
| `132` | Eucalyptus Lights | Meeting Rooms |
| `133` | Sequoia Lights | Meeting Rooms |
| `134` | A51-3 | Area 51 |
| `135` | A51-4 | Area 51 |
| `163` | Huddle 1 Lights | Huddle Rooms |
| `164` | Huddle 2 Lights | Huddle Rooms |
| `193` | Huddle 3 Lights | Huddle Rooms |
| `194` | Huddle 4 Lights | Huddle Rooms |
| `195` | Huddle 5 Lights | Huddle Rooms |
| `225` | Huddle 6 Lights | Huddle Rooms |
| `532` | A51 Hallway Sensor | Area 51 |
| `617` | Hickory Sensor | Hickory |

## Other Things That Command This Hardware

We are not the only consumer, and this matters when a switch changes state and
nothing in our logs explains why.

- **Maker API app `493`, "Maker API for Home Assistant"**, runs on `.51`
  alongside ours. It is a second programmable allowlist over the same hub, with
  its own token and its own device selection, and whatever holds that token can
  read and command those devices exactly as we can. Its token is not in
  `temperature-bot-config.yaml`, so **which devices it exposes is unverified** —
  this survey establishes that the app exists, not what it reaches.
- **Rule Machine, Motion Lighting, and Button Controller apps** run automations
  entirely inside the hubs. `.51` alone has ten Rule Machine rules and three
  motion-lighting apps. A light that turns itself off at sunrise is doing so
  because of a rule on the hub, not because of `app/rules_engine.py`.
- **Hubitat's own dashboards** are display surfaces for humans, on wall tablets
  and phones. Eight are installed across three hubs. A device on a dashboard is
  not thereby visible to us.
- **The Hue Bridge** (`BC6E12`, app `521` on `.51`) contributes 26 bulbs and 5
  groups in Hickory. Only the `581` group is exposed to us.
- **Mobile presence apps.** Several phones are registered as devices across the
  hubs. None are exposed to app `520`.

## Hub 10.2.3.51 — Somerville Area 51

The only hub in our configuration, and the only one our code can reach:
`temperature-bot-config.yaml` holds exactly one `hubitat.host` and one
`hubitat.appId`, so supporting a second hub would mean changing the
configuration model, not just adding a token.

83 devices are native to this hub; the other 37 are meshed in and listed in the
map above. In the table below `(shared)` marks a device shared outward to the mesh, and
`(520)` marks one exposed through app `520`.

| id | Hub room | Name | Protocol | Device type | Last seen |
| --- | --- | --- | --- | --- | --- |
| `129` | Area 51 | A51-1 `(shared)` `(520)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `130` | Area 51 | A51-2 `(shared)` `(520)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `134` | Area 51 | A51-3 `(shared)` `(520)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `135` | Area 51 | A51-4 `(shared)` `(520)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `321` | Area 51 | Area 51 East Column Outlet | Z-Wave | Generic Z-Wave Plus Outlet | 2025-06-25 |
| `364` | Area 51 | Garden Door Relay | Z-Wave | Zooz MultiRelay | 2026-08-17 |
| `365` | Area 51 | Garden Overhead Door | child | Generic Component Switch | 2026-08-17 |
| `366` | Area 51 | Garden Door Spare 2 | child | Generic Component Switch | 2025-07-18 |
| `367` | Area 51 | Garden Door Spare 3 | child | Generic Component Switch | 2025-07-18 |
| `421` | Area 51 | A51 Dimmer #1 | Z-Wave | Qubino Flush 0-10V Dimmer | 2026-08-20 |
| `422` | Area 51 | A51 Dimmer #2 | Z-Wave | Qubino Flush 0-10V Dimmer | 2026-08-20 |
| `450` | Area 51 | A51 Dimmer #3 | Z-Wave | Qubino Flush 0-10V Dimmer | 2026-08-20 |
| `451` | Area 51 | A51 Dimmer #4 | Z-Wave | Qubino Flush 0-10V Dimmer | 2026-08-20 |
| `453` | Area 51 | Area 51 Pendant Lights | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `481` | Area 51 | Area 51 Main Lights | software | Group Dimmer | 2026-08-20 |
| `517` | Area 51 | NO PULP | Z-Wave | Generic Z-Wave Plus Outlet | 2026-08-20 |
| `520` | Area 51 | Area 51 Meeting Rooms | software | Group Switch | 2026-06-10 |
| `532` | Area 51 | A51 Hallway Sensor `(shared)` `(520)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `534` | Area 51 | Water Sensor 2 | Z-Wave | Zooz ZSE42 Water Leak XS Sensor | 2026-08-20 |
| `571` | Area 51 | A51 Dimmer #5 | Z-Wave | Zooz Zen54 0-10V Dimmer | 2026-08-20 |
| `570` | Broadway | Broadway Washers | software | Group Switch | 2026-08-20 |
| `66` | Dungeon | Dungeon Ceiling `(shared)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `98` | Dungeon | Dungeon Cage `(shared)` `(520)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `384` | Dungeon | Dungeon Meter | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `449` | Dungeon | Dungeon Lights | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `518` | Dungeon | Dungeon Power Monitor | Z-Wave | Minoston Mini Power Meter Plug | 2026-08-20 |
| `562` | Dungeon | Dungeon Exhaust Fan | Z-Wave | Generic Z-Wave Plus Scene Switch | 2026-08-20 |
| `454` | Hickory | Green Wall - Inner `(520)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `550` | Hickory | Green Wall - Outer `(520)` | Z-Wave | Minoston MP31ZP Smart Plug | 2026-08-20 |
| `556` | Hickory | Hickory Lights | software | Group Switch | 2026-08-20 |
| `566` | Hickory | Hickory Lights Remote `(520)` | Z-Wave | Aeon WallMote | 2026-08-20 |
| `572` | Hickory | hueBridge BC6E12 (Hue Bridge) | software | hueBridge | 2026-08-20 |
| `581` | Hickory | Hickory Dimmable Lights `(520)` | software | hueBridgeGroup | 2026-08-20 |
| `605` | Hickory | Green Wall | software | Group Switch | 2026-08-20 |
| `606` | Hickory | Hickory Lights - Ceiling Front | software | hueBridgeGroup | 2026-08-20 |
| `607` | Hickory | Hickory Lights - Ceiling Rear | software | hueBridgeGroup | 2026-08-20 |
| `608` | Hickory | Hickory Lights - Left Wall | software | hueBridgeGroup | 2026-08-20 |
| `609` | Hickory | Hickory Lights - Right Wall | software | hueBridgeGroup | 2026-08-20 |
| `610` | Hickory | Hickory TV Up/Down Relay `(520)` | Z-Wave | Zooz ZEN17 Universal Relay Advanced | 2026-08-08 |
| `611` | Hickory | TV Up `(520)` | child | Generic Component Switch | 2026-08-08 |
| `612` | Hickory | TV Down `(520)` | child | Generic Component Switch | 2026-08-08 |
| `617` | Hickory | Hickory Sensor `(shared)` `(520)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `573` | Hickory Hue Bulbs | MS-A1 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `574` | Hickory Hue Bulbs | MS-A2 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `575` | Hickory Hue Bulbs | MS-A3 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `576` | Hickory Hue Bulbs | MS-A4 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `577` | Hickory Hue Bulbs | MS-A5 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `578` | Hickory Hue Bulbs | MS-A6 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `579` | Hickory Hue Bulbs | MS-A7 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `580` | Hickory Hue Bulbs | MS-A8 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `583` | Hickory Hue Bulbs | MS-B1 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `584` | Hickory Hue Bulbs | MS-B2 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `585` | Hickory Hue Bulbs | MS-B3 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `586` | Hickory Hue Bulbs | MS-B4 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `587` | Hickory Hue Bulbs | MS-B5 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `588` | Hickory Hue Bulbs | MS-B6 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `589` | Hickory Hue Bulbs | MS-B7 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `590` | Hickory Hue Bulbs | MS-B8 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `593` | Hickory Hue Bulbs | MS-C1 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `594` | Hickory Hue Bulbs | MS-C2 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `595` | Hickory Hue Bulbs | MS-C3 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `596` | Hickory Hue Bulbs | MS-C4 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `597` | Hickory Hue Bulbs | MS-C5 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `598` | Hickory Hue Bulbs | MS-D1 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `599` | Hickory Hue Bulbs | MS-D2 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `600` | Hickory Hue Bulbs | MS-D3 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `601` | Hickory Hue Bulbs | MS-D4 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `602` | Hickory Hue Bulbs | MS-D5 | software | hueBridgeBulbRGBW | 2026-08-20 |
| `163` | Huddle Rooms | Huddle 1 Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-20 |
| `164` | Huddle Rooms | Huddle 2 Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-19 |
| `193` | Huddle Rooms | Huddle 3 Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-19 |
| `194` | Huddle Rooms | Huddle 4 Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-19 |
| `195` | Huddle Rooms | Huddle 5 Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-19 |
| `225` | Huddle Rooms | Huddle 6 Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-19 |
| `420` | Huddle Rooms | Huddle 5 TV Power | Z-Wave | Generic Z-Wave Plus Outlet | 2026-08-11 |
| `101` | Meeting Rooms | Maple Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-20 |
| `131` | Meeting Rooms | Banyan Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-19 |
| `132` | Meeting Rooms | Eucalyptus Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-20 |
| `133` | Meeting Rooms | Sequoia Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-20 |
| `100` | Restrooms | Restroom Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-20 |
| `33` | Shower Room | Shower Room Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-20 |
| `539` | — | Carl's Nord N30 5G | software | Mobile App Device | 2026-04-09 |
| `615` | — | Carl's Pixel 10 Pro XL | software | Mobile App Device | 2026-04-09 |

### Apps on `.51`

- **`513` Basic Button Controllers**
  - `514` Basic Button Controller: Studio Lights Remote (7 rules)
- **`510` Easy Dashboards**
- **`353` Groups and Scenes**
  - `354` Area 51 Main Lights
  - `485` Area 51 Meeting Rooms
  - `519` Broadway Washers
  - `512` Hickory Lights
  - `527` Studio Lights - Green Wall
- **`65` Hubitat Z-Wave Mesh Details** — community app
- **`37` Hubitat® Dashboards**
  - `489` Area 51 Lights
  - `538` Hickory
  - `490` Somerville Office Doors + Fans
  - `130` Somerville Office Lights
  - `450` Somerville Office Sensors
- **`521` Hue Bridge Integration (BC6E12 - Hue Bridge)**
- **`493` Maker API for Home Assistant**
- **`520` Maker API for Temperature Bot**
- **`299` Motion and Mode Lighting Apps**
  - `321` Area 51 Motion
  - `300` Dungeon Motion
  - `541` Hickory Motion
- **`258` Notifications**
  - `486` Water Notifier
- **`417` Rebooter** — community app
- **`226` Rule Machine**
  - `228` Daily indoor lights off, outdoor lights on
  - `488` Daily Sunrise
  - `492` Dim Greenhouse
  - `386` Dungeon Exhaust Fan Off
  - `385` Dungeon Exhaust Fan On
  - `535` Hickory TV Down
  - `537` Hickory TV Up
  - `540` Movement anywhere to air1
  - `484` Power Restored
  - `227` Weekday Indoor Lights On

## Hub 10.2.3.52 — Somerville Broadway

Broadway, Lobby, Kitchen, and the outside lighting. This hub runs **no Maker API
app**, so it has no direct interface to us at all — everything we get from
Broadway arrives through `.51`: the Broadway sensors, the Data Closet fan and
sensor, the washers, and the TV carts.

Thirty-three of its forty devices are offered to the mesh, but only **29 are
actually linked onto `.51`**. Offering and linking are two steps, and the four
that stop at the first are `353`, `354`, `355`, and `356` — the window shades.
They are shared, nothing consumes them, and they do not appear anywhere in the
mesh map above.

Those four shades are also **the only Zigbee devices in the entire four-hub
estate**. Everything else on every hub is Z-Wave or software.

`(shared)` marks a device offered to the mesh. It does not mean anything linked
it.

| id | Hub room | Name | Protocol | Device type | Last seen |
| --- | --- | --- | --- | --- | --- |
| `3` | Bamboo | Bamboo Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-20 |
| `36` | Broadway | Broadway Sensor North `(shared)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `37` | Broadway | Broadway Sensor Center `(shared)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `97` | Broadway | Cedar Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-20 |
| `98` | Broadway | Willow Lights `(shared)` | Z-Wave | GE Z-Wave Plus Motion Switch | 2026-08-19 |
| `132` | Broadway | Broadway Lights `(shared)` | software | Group Switch | 2026-08-20 |
| `136` | Broadway | Garage Washer North `(shared)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `137` | Broadway | Data Closet Fan `(shared)` | Z-Wave | GE Smart Fan Control | 2026-08-20 |
| `138` | Broadway | Data Closet Sensor `(shared)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `151` | Broadway | Broadway Sensor South `(shared)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `291` | Broadway | Broadway Pendant Lights `(shared)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `293` | Broadway | Whiteboard Washer `(shared)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `294` | Broadway | Sidewalk Washer North `(shared)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `295` | Broadway | Sidewalk Washer South `(shared)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `297` | Broadway | Garage Washer South `(shared)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `353` | Broadway | Window Shade 2 `(shared)` | Zigbee | Generic Zigbee Shade | 2026-04-27 |
| `354` | Broadway | Window Shade 1 `(shared)` | Zigbee | Generic Zigbee Shade | 2026-04-27 |
| `355` | Broadway | Window Shade 3 `(shared)` | Zigbee | Generic Zigbee Shade | 2026-08-20 |
| `356` | Broadway | Window Shade 4 `(shared)` | Zigbee | Generic Zigbee Shade | 2026-08-20 |
| `385` | Broadway | Broadway Wall Controller | Z-Wave | Aeon WallMote | 2026-08-20 |
| `387` | Broadway | Broadway Power Monitor `(shared)` | Z-Wave | Minoston Mini Power Meter Plug | 2026-08-20 |
| `393` | Broadway | Broadway Spot Lights `(shared)` | Z-Wave | Minoston Mini Power Meter Plug | 2026-08-20 |
| `395` | Broadway | Broadway TV Cart Left `(shared)` | Z-Wave | Generic Z-Wave Plus Outlet | 2026-08-20 |
| `396` | Broadway | Broadway TV Cart Right `(shared)` | Z-Wave | Generic Z-Wave Plus Outlet | 2026-08-17 |
| `40` | Kitchen | Kitchen Counter Lights `(shared)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `225` | Kitchen | Jura Coffee Maker | Z-Wave | Enerwave Metering Switch ZW15RM-Plus | 2026-08-20 |
| `290` | Kitchen | Kitchen Main Lights `(shared)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `38` | Lobby | Lobby Sensor `(shared)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `65` | Lobby | Lobby Short Grazers `(shared)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `66` | Lobby | Lobby Long Grazers `(shared)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `133` | Lobby | Lobby Lights `(shared)` | software | Group Switch | 2026-08-20 |
| `289` | Lobby | Lobby Main Lights `(shared)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `386` | Lobby | Lobby Wall Controller | Z-Wave | Aeon WallMote | 2026-08-20 |
| `134` | Outside | Outside Lights | software | Group Switch | 2026-08-20 |
| `141` | Outside | Garden Lights `(shared)` | Z-Wave | Generic Z-Wave Plus Outlet | 2026-08-20 |
| `257` | Outside | Column Lights Color | Z-Wave | Qubino Flush 0-10V Dimmer | 2026-04-22 |
| `292` | Outside | Main Entrance Lights `(shared)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `296` | Outside | Column & Sidewalk Lights `(shared)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `392` | — | Carl's Nord N30 5G | software | Mobile App Device | 2026-04-09 |
| `394` | — | Pixel 10 Pro XL | software | Mobile App Device | 2026-06-21 |

### Apps on `.52`

- **`417` Button Controllers**
  - `418` Broadway (4 rules)
  - `423` Lobby (4 rules)
- **`97` Groups and Scenes**
  - `161` Broadway Lights
  - `162` Lobby Lights
  - `163` Outside Lights
- **`36` Hubitat Z-Wave Mesh Details** — community app
- **`437` Hubitat® Dashboards**
  - `449` Broadway Controls
- **`225` Motion and Mode Lighting Apps**
  - `257` Broadway Motion
- **`131` Notifications**
  - `132` Nightime Lighting Check
  - `430` Power Notifier
- **`353` Rebooter** — community app
- **`100` Rule Machine**
  - `432` Daily Modes
  - `102` Daily Sunrise
  - `103` Daily Sunset
  - `448` Data Closet Fan Off
  - `447` Data Closet Fan On
  - `169` Lobby Motion Daytime
  - `165` Lobby Motion Evening

## Hub 10.2.3.53 — Somerville Greenhouse

The smallest of the office hubs: the Greenhouse itself, plus the Lobby color
and intensity dimmers. Eight of its eleven devices are shared up to `.51`; two
of those, the Greenhouse East and West sensors, are exposed to us. Like `.52` it
runs no Maker API app.

| id | Hub room | Name | Protocol | Device type | Last seen |
| --- | --- | --- | --- | --- | --- |
| `3` | Greenhouse | Greenwall White Lights `(shared)` | Z-Wave | Generic Z-Wave Plus Scene Switch | 2026-08-20 |
| `4` | Greenhouse | Greenwall Yellow Lights `(shared)` | Z-Wave | Generic Z-Wave Plus Scene Switch | 2026-08-20 |
| `34` | Greenhouse | Greenhouse Sensor West `(shared)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `35` | Greenhouse | Greenhouse Sensor East `(shared)` | Z-Wave | AeotecMultiSensor6 | 2026-08-20 |
| `36` | Greenhouse | Greenhouse Intensity `(shared)` | Z-Wave | Qubino Flush 0-10V Dimmer | 2026-08-20 |
| `97` | Greenhouse | Greenhouse Main Lights `(shared)` | Z-Wave | GE Enbrighten Z-Wave Smart Switch | 2026-08-20 |
| `129` | Greenhouse | Greenhouse | Z-Wave | Aeon WallMote | 2026-08-06 |
| `65` | Lobby | Lobby Color `(shared)` | Z-Wave | Qubino Flush 0-10V Dimmer | 2026-08-20 |
| `66` | Lobby | Lobby Intensity `(shared)` | Z-Wave | Qubino Flush 0-10V Dimmer | 2026-08-20 |
| `131` | — | Carl's Nord N30 5G | software | Mobile App Device | never |
| `132` | — | Leo’s iPhone 15 Pro | software | Mobile App Device | never |

### Apps on `.53`

- **`101` Button Controllers**
  - `102` Button Controller-5.1: Greenhouse (4 rules)
- **`114` Hubitat® Dashboards**
- **`38` Motion and Mode Lighting Apps**
  - `39` Greenhouse Motion
- **`65` Rebooter** — community app
- **`3` Rule Machine**
  - `34` Greenwall Both
  - `33` Greenwall Cool
  - `35` Greenwall Sleep
  - `36` Greenwall Warm

## Hub 10.2.3.54 — CALA Garage

A garage installation: parking-spot temperature sensors and spot heaters, plus
sensors at the vehicle and pedestrian entrances. Every device is on this hub's
own Z-Wave radio, in a single Hubitat room called "0F Garage".

**This hub is completely isolated.** It shares nothing to the mesh, no other hub
has a linked device from it, and it runs no Maker API app. There is no path by
which Temperature Bot could read a single value from it, and none by which it
could read anything from us. Its Z-Wave Poller app is disabled.

It is also the least healthy hub in the building: ten of its fifteen devices
have not reported activity in more than a month, and `Spot 16 Sensor` last spoke
in June 2025. Whether that is a fault or simply seasonal — spot heaters have no
reason to report in August — is not something this survey can tell you.

| id | Hub room | Name | Protocol | Device type | Last seen |
| --- | --- | --- | --- | --- | --- |
| `3` | 0F Garage | Spot 10 Sensor | Z-Wave | Aeotec MultiSensor 7 | 2026-05-15 |
| `4` | 0F Garage | Spot 27-28 Sensor | Z-Wave | Aeotec MultiSensor 7 | 2026-08-20 |
| `5` | 0F Garage | Spot 30 Sensor | Z-Wave | Aeon Multisensor 6 | 2026-08-20 |
| `6` | 0F Garage | Spot 22 Heater | Z-Wave | Generic Z-Wave Smart Switch | 2026-08-09 |
| `7` | 0F Garage | Spot 27 Heater | Z-Wave | Generic Z-Wave Smart Switch | 2026-07-07 |
| `38` | 0F Garage | Garage Entrance Sensor | Z-Wave | Aeon Multisensor 6 | 2026-08-20 |
| `39` | 0F Garage | Spot 16 Sensor | Z-Wave | Aeotec MultiSensor 7 | 2025-06-05 |
| `40` | 0F Garage | Sensor A | Z-Wave | Aeotec MultiSensor 7 | 2026-08-20 |
| `41` | 0F Garage | Spot 10 Heater | Z-Wave | Generic Z-Wave Smart Switch | 2026-05-07 |
| `42` | 0F Garage | Spot 33 Heater | Z-Wave | Generic Z-Wave Smart Switch | 2026-05-07 |
| `43` | 0F Garage | Spot 16 Heater | Z-Wave | Generic Z-Wave Smart Switch | 2026-05-07 |
| `44` | 0F Garage | Spot 31 Heater | Z-Wave | Generic Z-Wave Smart Switch | 2026-05-07 |
| `45` | 0F Garage | Vehicle Entrance Heater Out | Z-Wave | Generic Z-Wave Smart Switch | 2026-05-07 |
| `46` | 0F Garage | Package Room Heater | Z-Wave | Generic Z-Wave Smart Switch | 2026-05-07 |
| `47` | 0F Garage | Vehicle Entrance Heater In | Z-Wave | Generic Z-Wave Smart Switch | 2026-05-07 |

### Apps on `.54`

- **`1` Basic Rules**
- **`2` Hubitat® Dashboards**
  - `27` Garage
- **`28` Visual Rules Builder**
- **`6` Z-Wave Poller** — **disabled** (its name carries a "Polling" status badge)

## Health Notes

Nothing here is an alarm. These are the things a reader of the tables above
would reasonably want flagged.

**A platform update is pending on all four hubs** — 2.5.0.159 installed,
2.5.1.152 available. Applying it to `.51` interrupts collection.

**Devices that have gone quiet.** Long silence is not automatically a fault: a
switch that nobody touches reports nothing, and a spot heater in August has
nothing to say. These are simply the ones a health check would surface.

| Hub | Device | Last activity |
| --- | --- | --- |
| `.54` | Spot 16 Sensor | 2025-06-05 |
| `.51` | Area 51 East Column Outlet | 2025-06-25 |
| `.51` | Garden Door Spare 2, Garden Door Spare 3 | 2025-07-18 |
| `.51` | Carl's Nord N30 5G, Carl's Pixel 10 Pro XL | 2026-04-09 |
| `.51` | Area 51 Meeting Rooms (a group, not hardware) | 2026-06-10 |
| `.52` | Column Lights Color | 2026-04-22 |
| `.52` | Window Shade 1, Window Shade 2 | 2026-04-27 |
| `.54` | Spot 10 Sensor | 2026-05-15 |
| `.54` | Eight spot and entrance heaters | 2026-05-07 to 2026-07-07 |
| `.53` | Two registered phones | never |

That is the complete set for `.51`, the hub we depend on. **None of those six is
exposed through app `520`**, so no reading we store is affected by any of them.
For `.52`, `.53`, and `.54` the table is a selection; each hub's inventory above
carries a last-seen date for every device.

**Database sizes** are 13 MB on `.51`, 5 MB on `.52`, 4 MB on `.54`, 1 MB on
`.53`, with no `hubLargeishDatabase` alert anywhere.

## Re-running This Survey

Every table in this file comes from four read-only HTTP endpoints. The hubs
require no authentication on the LAN, except for Maker API, which takes the
token from `temperature-bot-config.yaml` under `secrets.hubitat.access_token`.

```bash
# Per hub: identity, model, firmware, alerts
curl -s http://10.2.3.51/hub2/hubData | python3 -m json.tool

# Per hub: every device, meshed ones included, with child devices nested
curl -s http://10.2.3.51/hub2/devicesList | python3 -m json.tool

# Per hub: installed apps, nested parent -> child -> rule
curl -s http://10.2.3.51/hub2/appsList | python3 -m json.tool

# What app 520 exposes — the only list that describes our reach
curl -s "http://10.2.3.51/apps/api/520/devices/all?access_token=$TOKEN" \
  | python3 -c 'import json,sys; [print(d["id"], d["label"]) for d in json.load(sys.stdin)]'
```

Two fields do the heavy lifting. A device with `"source": "Linked"` was meshed
in from another hub, and its `remoteDeviceUrl` names that hub and the id it
holds there — that pair is the whole mesh map. A device with `"hubMesh": true`
is shared *outward*, which is the opposite relationship and easy to misread.

Notes on doing this safely:

- Everything above is a GET. Keep it that way. In particular do not open
  `http://10.2.3.51/installedapp/configure/520/mainPage` just to look: the app
  inventory is available from `hub2/appsList`, and that page carries a "Create
  New Access Token" button that would invalidate the token in our config and
  stop all collection.
- `hub2/hubData` returns the hub's dashboard access token and the registered
  account email. Do not paste raw responses into commits, issues, or documents.
- `python -m app.hubitat --list-devices` will not answer any of these questions.
  Despite the name it filters to devices reporting a temperature, so it cannot
  see a switch, outlet, or fan at all.
