#!/usr/bin/env python3
"""
Simple test to check if Flask routes are working
"""
# pylint: disable=unused-import
from conftest import client_with_db  # noqa: F401

def test_status_endpoint(client_with_db): # noqa: F811
    response = client_with_db.get("/api/v1/status")
    assert response.status_code == 200
