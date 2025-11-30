"""
Configuration for room dashboards (kitchen/studio)
Each room specifies which ERVs, fans, and sensors to display
"""

ROOM_CONFIGS = {
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
    "studio": {
        "url": "/studio",
        "ervs": ["ERV Restrooms"],
        "fans": ["Area 51", "Dungeon"],
        "sensors": [
            "A51 Sensor 1",
            "A51 Sensor 2",
            "A51 Sensor 3",
            "A51 Sensor 4",
            "A51 Hallway",
            "Cage Sensor",
        ],
    },
}
