"""
Configuration for room dashboards (kitchen/hickory).

Each room specifies which ERVs, fans, and sensors to display.
All device names must match exactly with names in the database or Hubitat.
"""

from typing import Dict, Any

RoomConfig = Dict[str, Any]
"""Type alias for room configuration dict.
Keys: 'url' (str), 'ervs' (list[str]), 'fans' (list[str]), 'sensors' (list[str])
"""

ROOM_CONFIGS: Dict[str, RoomConfig] = {
    "kitchen": {
        "url": "/kitchen",
        "ervs": ["ERV Kitchen"],
        "fans": [],
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
        "fans": ["Area 51", "Dungeon"],
        "sensors": [
            "Hickory Sensor",
            "Dungeon Cage",
        ],
        "tv_control": True,
    },
}
