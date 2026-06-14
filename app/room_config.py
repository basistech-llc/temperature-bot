"""Configuration for room dashboards (kitchen/hickory).

Each room specifies which ERVs, fans, and sensors to display.
All device names must match exactly with names in the database or Hubitat.
"""

from .models import RoomConfig

EMPTY_ROOM_CONFIG = RoomConfig(url="")

ROOM_CONFIGS: dict[str, RoomConfig] = {
    "kitchen": RoomConfig(
        url="/kitchen",
        ervs=["ERV Kitchen"],
        fans=["Kitchen"],
        sensors=[
            "Lobby Sensor on Somerville Broadway",
            "Broadway Sensor Center on Somerville Broadway",
            "Broadway Sensor North on Somerville Broadway",
            "Broadway Sensor South on Somerville Broadway",
        ],
    ),
    "hickory": RoomConfig(
        url="/hickory",
        ervs=["ERV Restrooms"],
        fans=["Restrooms/BOH", "Dungeon"],
        sensors=[
            "Hickory Sensor",
            "Dungeon Cage",
        ],
        tv_control=True,
        dimmer_id="581",
        wall_inner_id="454",
        wall_outer_id="550",
    ),
}


def get_room_config(room_key: str) -> RoomConfig:
    """Return room dashboard configuration, or an empty config for unknown rooms."""
    return ROOM_CONFIGS.get(room_key, EMPTY_ROOM_CONFIG)
