"""
test airnow endpoint
"""
import logging
from unittest.mock import patch
import os
import pytest

from app import airnow

logger = logging.getLogger(__name__)

skip_on_github = pytest.mark.skipif(os.getenv("GITHUB_ACTIONS") == "true", reason="Disabled in GitHub Actions")

@skip_on_github
@patch("app.airnow.get_aqi")
def test_get_aqi(mock_get_aqi):
    # Mock the return value
    mock_get_aqi.return_value = 45

    result = airnow.aqi_decode(airnow.get_aqi())
    assert isinstance(result, dict)
    assert "value" in result
    assert result["value"] == 45
    assert result["name"] == "Good"
    logging.info("get_aqi: %s", result)
