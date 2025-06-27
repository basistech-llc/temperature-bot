import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest

import myapp.ae200 as ae200
import myapp.aqi as aqi
from myapp.app import status, set_speed, SpeedRequest

import logging
logger = logging.getLogger(__name__)

# Optional: enable pytest-asyncio
pytest_plugins = ("pytest_asyncio",)

# Use pytest-asyncio to allow async test functions
@pytest.mark.asyncio
async def test_get_aqi_sync():
    result = aqi.get_aqi_sync()
    assert isinstance(result, dict)
    assert "value" in result
    logging.info("get_aqi_sync: %s", result)

@pytest.mark.asyncio
async def test_get_erv_status():
    result = await ae200.get_erv_status()
    assert isinstance(result, dict)
    logging.info(" get_erv_status: %s", result)

@pytest.mark.asyncio
async def test_status_endpoint():
    response = await status()
    assert "AQI" in response and "ERV" in response
    logging.info(" /status: %s", response)

@pytest.mark.asyncio
@pytest.mark.parametrize("unit,speed", [
    (12, 0),
    (12, 1),
    (13, 2),
])
@patch("myapp.ae200.set_erv_speed", new_callable=AsyncMock)
async def test_set_speed_endpoint(mock_set_speed, unit, speed):
    req = SpeedRequest(unit=unit, speed=speed)
    response = await set_speed(req)

    assert response["status"] == "ok"
    assert response["unit"] == unit
    assert response["speed"] == speed
    mock_set_speed.assert_awaited_once_with(unit, speed)

    logging.info("/set_speed (unit=%s, speed=%s):", unit,speed)
