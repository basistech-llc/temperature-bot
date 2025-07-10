#!/usr/bin/env python3
"""
Simple test to check if FastAPI routes are working
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager
from app.main import app as fastapi_app

@pytest_asyncio.fixture
async def async_client():
    # Manage lifespan manually
    async with LifespanManager(fastapi_app):
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac

@pytest.mark.asyncio
async def test_status_endpoint(async_client):
    response = await async_client.get("/api/v1/status")
    assert response.status_code == 200
