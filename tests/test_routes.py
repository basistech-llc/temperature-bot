#!/usr/bin/env python3
"""
Simple test to check if Flask routes are working
"""
# pylint: disable=unused-import
from conftest import flask_test_client  # noqa: F401

def test_status_endpoint(flask_test_client): # noqa: F811
    response = flask_test_client.get("/api/v1/status")
    assert response.status_code == 200
