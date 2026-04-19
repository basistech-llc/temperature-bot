"""
Configuration for room dashboards (kitchen/hickory).

Each room specifies which ERVs, fans, and sensors to display.
All device names must match exactly with names in the database or Hubitat.
"""

from typing import Dict, Any

RoomConfig = Dict[str, Any]
"""Type alias for room configuration dict.
Keys: 'url' (str), 'ervs' (list[str]), 'fans' (list[str]), 'sensors' (list[str]),
'tv_control' (bool), 'dimmer_id' (str), 'wall_inner_id' (str), 'wall_outer_id' (str)
"""

ROOM_CONFIGS: Dict[str, RoomConfig] = {
    "kitchen": {
        "url": "/kitchen",
        "ervs": ["ERV Kitchen"],
        "fans": ["Kitchen"],
        "sensors": [
            "Lobby Sensor on Somerville Broadway",
            "Broadway Sensor Center on Somerville Broadway",
            "Broadway Sensor North on Somerville Broadway",
            "Broadway Sensor South on Somerville Broadway",
        ],
    },
    "hickory": {
        "url": "/hickory",
        "ervs": ["ERV Restrooms"],
        "fans": ["Area 51", "Restrooms/BOH", "Dungeon"],
        "sensors": [
            "Hickory Sensor",
            "Dungeon Cage",
        ],
        "tv_control": True,
        "dimmer_id": "581",
        "wall_inner_id": "454",
        "wall_outer_id": "550",
    },
}
