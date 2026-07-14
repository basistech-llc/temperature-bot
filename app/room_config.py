"""Configuration for room dashboards (kitchen/hickory).

Each legacy dashboard specifies actuator controls. Sensor membership comes from
canonical ``devices.room_id`` assignments.
"""

from .models import RoomConfig

EMPTY_ROOM_CONFIG = RoomConfig(url="")

ROOM_CONFIGS: dict[str, RoomConfig] = {
    "kitchen": RoomConfig(
        url="/kitchen",
        ervs=["ERV Kitchen"],
        fans=["Kitchen"],
    ),
    "hickory": RoomConfig(
        url="/hickory",
        ervs=["ERV Restrooms"],
        fans=["Restrooms/BOH", "Dungeon"],
        tv_control=True,
        tv_up_label="TV Up",
        tv_down_label="TV Down",
        dimmer_id="581",
        wall_inner_id="454",
        wall_outer_id="550",
    ),
}


def get_room_config(room_key: str) -> RoomConfig:
    """Return room dashboard configuration, or an empty config for unknown rooms."""
    return ROOM_CONFIGS.get(room_key, EMPTY_ROOM_CONFIG)
