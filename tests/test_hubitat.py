"""
test hubitat.py
"""

import logging
from os.path import join
import json

from app import hubitat
from app.paths import ETC_DIR

logger = logging.getLogger(__name__)

HUBITAT_JSON = join(ETC_DIR, "sample_hubitat.json")

def test_hubitat():
    """
    Sets up the database schema on a given connection by reading from schema.sql.
    """
    with open(HUBITAT_JSON, "r") as f:
        hubdict = json.load(f)
    temps = hubitat.extract_temperatures(hubdict)
    assert len(temps) == 15
    count = 0
    for t in temps:
        if t['name'] == 'A51 Sensor 3':
            assert t['temperature'] == "23.4"
            count += 1
    assert count == 1
