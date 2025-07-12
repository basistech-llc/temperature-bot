#!/usr/bin/env python3
"""
Simple test to check if Flask routes are working
"""
# pylint: disable=unused-import
from fixtures import client  # noqa: F401

def test_status_endpoint(client): # noqa: F811
    response = client.get("/api/v1/status")
    assert response.status_code == 200
