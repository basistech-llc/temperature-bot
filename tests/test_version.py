"""Tests for app.version (display string and git SHA lookup) and the
version-reporting endpoints."""

import subprocess
from unittest.mock import patch

from conftest import flask_test_client  # noqa: F401  # pylint: disable=unused-import

from app import version
from app.version import __version__


def test_display_version_with_sha():
    with patch("app.version.git_sha", return_value="abc1234"):
        assert version.display_version() == f"v{__version__} (git sha: abc1234)"


def test_display_version_without_sha():
    with patch("app.version.git_sha", return_value=None):
        assert version.display_version() == f"v{__version__}"


def test_git_sha_returns_short_sha():
    version.git_sha.cache_clear()
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="abc1234\n")
    try:
        with patch("app.version.subprocess.run", return_value=completed):
            assert version.git_sha() == "abc1234"
    finally:
        version.git_sha.cache_clear()


def test_git_sha_handles_missing_git():
    version.git_sha.cache_clear()
    try:
        with patch("app.version.subprocess.run", side_effect=FileNotFoundError):
            assert version.git_sha() is None
    finally:
        version.git_sha.cache_clear()


def test_version_page(flask_test_client):  # noqa: F811
    response = flask_test_client.get("/version")
    assert response.status_code == 200
    assert response.data.decode("utf-8") == f"version: {version.display_version()}"


def test_api_version(flask_test_client):  # noqa: F811
    response = flask_test_client.get("/api/v1/version")
    assert response.status_code == 200
    assert response.json == {"version": __version__, "sha": version.git_sha()}


def test_about_page_shows_version(flask_test_client):  # noqa: F811
    response = flask_test_client.get("/about")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    # Version appears in the footer (the duplicate body line was removed).
    assert version.display_version() in html
    assert "about-version" not in html
