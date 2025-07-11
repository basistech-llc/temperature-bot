#!/usr/bin/env python3
"""
Simple test to check if Flask routes are working
"""
import pytest
from app.main import app as flask_app

@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        yield client

def test_status_endpoint(client):
    response = client.get("/api/v1/status")
    assert response.status_code == 200
