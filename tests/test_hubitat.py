import logging
#from unittest.mock import AsyncMock, patch
#import sqlite3
#import os
from os.path import join
import json
#import time
#import pytest_asyncio
#import pytest
#import tempfile # Import tempfile
#import shutil   # Import shutil for directory cleanup

#from fastapi.testclient import TestClient
# from contextlib import asynccontextmanager # Not directly used on override_get_db_connection

import myapp.hubitat as hubitat

#from myapp.main import app as fastapi_app
#import myapp.ae200 as ae200
#import myapp.aqi as aqi
#import myapp.db as db
from myapp.paths import ETC_DIR

#from myapp.main import status, set_speed, SpeedControl

logger = logging.getLogger(__name__)

# Optional: enable pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


HUBITAT_JSON =join(ETC_DIR,"sample_hubitat.json")

def test_hubitat():
    """
    Sets up the database schema on a given connection by reading from schema.sql.
    """
    with open(HUBITAT_JSON,"r") as f:
        hubdict = json.load(f)
    temps = hubitat.extract_temperatures(hubdict)
    assert len(temps) == 15
    count = 0
    for t in temps:
        if t['name']=='A51 Sensor 3':
            assert t['temperature'] == "23.4"
            count  += 1
    assert count==1
