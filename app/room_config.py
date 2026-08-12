"""Configuration for room dashboards.

Sensor tiles are not configured here. They come from canonical
``devices.room_id`` assignments; ``members`` only selects which rooms' sensors a
dashboard gathers. What is configured here is deliberate presentation: which
AE-200 units and which Hubitat actuators a dashboard offers.

A ``members`` entry is matched against a room name or against the device name of
the FCU that owns the room. Prefer the FCU name where one exists: FCU names are
hardware identity and survive a room rename, while a room with no FCU (Garage,
Data Closet) can only be named directly.
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
    # Every control below is a device on Hubitat hub 10.2.3.52. We only reach
    # 10.2.3.51 (Maker API app 520), so these tiles read as unavailable until
    # the devices are exposed there. See doc/hardware-landscape.md.
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
                device_id="395",
            ),
            RoomControl(
                key="tv-cart-right",
                kind=RoomControlKind.SWITCH,
                label="TV Cart Right",
                device_id="396",
            ),
            RoomControl(
                key="pendant-lights",
                kind=RoomControlKind.SWITCH,
                label="Pendant Lights",
                device_id="291",
            ),
            RoomControl(
                key="spot-lights",
                kind=RoomControlKind.SWITCH,
                label="Spot Lights",
                device_id="393",
            ),
            RoomControl(
                key="whiteboard-washer",
                kind=RoomControlKind.SWITCH,
                label="Whiteboard Washer",
                device_id="293",
            ),
            RoomControl(
                key="sidewalk-washer-north",
                kind=RoomControlKind.SWITCH,
                label="Sidewalk Washer North",
                device_id="294",
            ),
            RoomControl(
                key="sidewalk-washer-south",
                kind=RoomControlKind.SWITCH,
                label="Sidewalk Washer South",
                device_id="295",
            ),
            RoomControl(
                key="garage-washer-north",
                kind=RoomControlKind.SWITCH,
                label="Garage Washer North",
                device_id="136",
            ),
            RoomControl(
                key="garage-washer-south",
                kind=RoomControlKind.SWITCH,
                label="Garage Washer South",
                device_id="297",
            ),
            RoomControl(
                key="data-closet-fan",
                kind=RoomControlKind.FAN,
                label="Data Closet Fan",
                device_id="137",
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
