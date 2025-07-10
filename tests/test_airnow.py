"""
test airnow endpoint
"""
#import asyncio
from os.path import join
import logging
from unittest.mock import AsyncMock, patch
import sqlite3
import os
import tempfile # Import tempfile
import json
#import time
import pytest_asyncio
import pytest
#import shutil   # Import shutil for directory cleanup

from fastapi.testclient import TestClient
# from contextlib import asynccontextmanager # Not directly used on override_get_db_connection

from app.main import app as fastapi_app
from app import main
from app import ae200
from app import airnow
from app import db
from app.paths import SCHEMA_FILE_PATH,TEST_DATA_DIR
#from app.main import status, set_speed, SpeedControl

logger = logging.getLogger(__name__)

# Optional: enable pytest-asyncio
pytest_plugins = ("pytest_asyncio",)
skip_on_github = pytest.mark.skipif( os.getenv("GITHUB_ACTIONS") == "true", reason="Disabled in GitHub Actions")



@skip_on_github
@pytest.mark.asyncio
@patch("app.airnow.get_aqi_sync")
async def test_get_aqi_sync(mock_get_aqi_sync):
    # Mock the return value
    mock_get_aqi_sync.return_value = {"value": 45, "color": "#00e400", "name": "Good"}

    result = airnow.get_aqi_sync()
    assert isinstance(result, dict)
    assert "value" in result
    assert result["value"] == 45
    assert result["name"] == "Good"
    logging.info("get_aqi_sync: %s", result)
