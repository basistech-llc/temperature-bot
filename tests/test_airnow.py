"""
test airnow endpoint
"""
from os.path import join
import logging
from unittest.mock import patch
import sqlite3
import os
import tempfile
import json
import pytest

from app import airnow

logger = logging.getLogger(__name__)

skip_on_github = pytest.mark.skipif(os.getenv("GITHUB_ACTIONS") == "true", reason="Disabled in GitHub Actions")

@skip_on_github
@patch("app.airnow.get_aqi_sync")
def test_get_aqi_sync(mock_get_aqi_sync):
    # Mock the return value
    mock_get_aqi_sync.return_value = {"value": 45, "color": "#00e400", "name": "Good"}

    result = airnow.get_aqi_sync()
    assert isinstance(result, dict)
    assert "value" in result
    assert result["value"] == 45
    assert result["name"] == "Good"
    logging.info("get_aqi_sync: %s", result)
