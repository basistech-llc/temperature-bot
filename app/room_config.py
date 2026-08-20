"""Configuration for room dashboards.

Sensor tiles are not configured here. They come from canonical
``devices.room_id`` assignments; ``members`` only selects which rooms' sensors a
dashboard gathers. What is configured here is deliberate presentation: which
AE-200 units and which Hubitat actuators a dashboard offers.

A ``members`` entry is matched against a room name or against the device name of
the FCU that owns the room. Prefer the FCU name where one exists: FCU names are
hardware identity and survive a room rename, while a room with no FCU (Garage,
Data Closet) can only be named directly.

Every ``device_id`` here is a device id **on hub 10.2.3.51**, the hub configured
in ``temperature-bot-config.yaml``. Ids are per hub and are not interchangeable:
the same physical sensor carries different ids on each hub it is meshed onto, so
an id copied from another hub's dashboard is at best dead and at worst names a
different device. Read ids from that hub, for example with
``poetry run python -m app.hubitat --list-devices``.
"""

from .models import RoomConfig, RoomControl, RoomControlKind

EMPTY_ROOM_CONFIG = RoomConfig(url="")

ROOM_CONFIGS: dict[str, RoomConfig] = {
    "kitchen": RoomConfig(
        url="/kitchen",
        label="Kitchen",
        members=["kitchen"],
        ervs=["ERV Kitchen"],
        fans=["Kitchen"],
    ),
    "hickory": RoomConfig(
        url="/hickory",
        label="Hickory",
        members=["hickory"],
        ervs=["ERV Restrooms"],
        fans=["Restrooms/BOH", "Dungeon"],
        controls=[
            RoomControl(
                key="tv",
                kind=RoomControlKind.TV,
                label="TV",
                up_label="TV Up",
                down_label="TV Down",
            ),
            RoomControl(
                key="main",
                kind=RoomControlKind.DIMMER,
                label="Main Lights",
                device_id="581",
            ),
            # Keyed "inner"/"outer" because that is what the wall-light request
            # body has always sent as its control key.
            RoomControl(
                key="inner",
                kind=RoomControlKind.SWITCH,
                label="Green Wall - Inner",
                device_id="454",
            ),
            RoomControl(
                key="outer",
                kind=RoomControlKind.SWITCH,
                label="Green Wall - Outer",
                device_id="550",
            ),
        ],
    ),
    # Broadway spans four canonical rooms: the space is served by two FCUs, and
    # each FCU owns its own room, so there is deliberately no single "Broadway"
    # room to address. The Garage and Sidewalk switches are just outside the
    # space and are driven from here on purpose.
    #
    # These ids came originally from the Hubitat dashboard on hub 10.2.3.52 and
    # were wrong: device ids are per hub, and three of them named unrelated
    # devices here (.52's 291 "Broadway Pendant Lights" is 291 "Kitchen Counter
    # Lights" on .51). They are now the ids on 10.2.3.51, the only hub we reach.
    # The two TV Cart switches still carry no id. They have since been meshed
    # onto .51 (618 and 619, source "Linked" in /hub2/devicesList), but Maker
    # API app 520 does not expose them yet, so /devices/618 answers "Device not
    # found or not authorized" and there is nothing here to address. Naming 618
    # anyway would render the tiles live and let them fail on click, which is
    # the hazard these notes exist to avoid. They stay as visibly unavailable
    # tiles until the two boxes are ticked in app 520.
    "broadway": RoomConfig(
        url="/broadway",
        label="Broadway",
        members=["Broadway North", "Broadway South", "Data Closet", "Garage"],
        fans=["Broadway North", "Broadway South"],
        controls=[
            RoomControl(
                key="tv-cart-left",
                kind=RoomControlKind.SWITCH,
                label="TV Cart Left",
                unavailable_note=(
                    "Meshed onto 10.2.3.51 as device 618, but not exposed by Maker API 520"
                ),
            ),
            RoomControl(
                key="tv-cart-right",
                kind=RoomControlKind.SWITCH,
                label="TV Cart Right",
                unavailable_note=(
                    "Meshed onto 10.2.3.51 as device 619, but not exposed by Maker API 520"
                ),
            ),
            RoomControl(
                key="pendant-lights",
                kind=RoomControlKind.SWITCH,
                label="Pendant Lights",
                device_id="260",
            ),
            RoomControl(
                key="spot-lights",
                kind=RoomControlKind.SWITCH,
                label="Spot Lights",
                device_id="616",
            ),
            RoomControl(
                key="whiteboard-washer",
                kind=RoomControlKind.SWITCH,
                label="Whiteboard Washer",
                device_id="356",
            ),
            RoomControl(
                key="sidewalk-washer-north",
                kind=RoomControlKind.SWITCH,
                label="Sidewalk Washer North",
                device_id="354",
            ),
            RoomControl(
                key="sidewalk-washer-south",
                kind=RoomControlKind.SWITCH,
                label="Sidewalk Washer South",
                device_id="355",
            ),
            RoomControl(
                key="garage-washer-north",
                kind=RoomControlKind.SWITCH,
                label="Garage Washer North",
                device_id="360",
            ),
            RoomControl(
                key="garage-washer-south",
                kind=RoomControlKind.SWITCH,
                label="Garage Washer South",
                device_id="361",
            ),
            RoomControl(
                key="data-closet-fan",
                kind=RoomControlKind.FAN,
                label="Data Closet Fan",
                device_id="359",
            ),
        ],
    ),
}


def get_room_config(room_key: str) -> RoomConfig:
    """Return room dashboard configuration, or an empty config for unknown rooms."""
    return ROOM_CONFIGS.get(room_key, EMPTY_ROOM_CONFIG)


def find_room_config(room_key: str) -> RoomConfig | None:
    """Return an explicitly configured room, preserving unknown-room identity."""
    return ROOM_CONFIGS.get(room_key)
