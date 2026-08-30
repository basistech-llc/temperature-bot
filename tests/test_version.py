"""Tests for version metadata."""

import subprocess

from conftest import flask_test_client  # noqa: F401  # pylint: disable=unused-import

from app import version
from app.main import app


def test_version_file_is_source_of_truth():
    assert version.__version__ == version.VERSION_FILE.read_text(
        encoding="utf-8"
    ).strip()


def test_git_sha_returns_current_checkout():
    version.git_sha.cache_clear()
    try:
        result = subprocess.run(
            ["git", "-C", str(version.REPO_ROOT), "rev-parse", "--short=12", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=1,
        )
        assert version.git_sha() == result.stdout.strip()
    finally:
        version.git_sha.cache_clear()


def test_git_branch_returns_current_checkout():
    version.git_branch.cache_clear()
    try:
        result = subprocess.run(
            ["git", "-C", str(version.REPO_ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=1,
        )
        assert version.git_branch() == result.stdout.strip()
    finally:
        version.git_branch.cache_clear()


def test_version_page(flask_test_client):  # noqa: F811
    response = flask_test_client.get("/version")
    assert response.status_code == 200
    assert response.data.decode("utf-8") == f"version: {version.__version__}"


def test_api_version(flask_test_client):  # noqa: F811
    response = flask_test_client.get("/api/v1/version")
    assert response.status_code == 200
    assert response.json == {
        "version": version.__version__,
        "sha": version.git_sha(),
        "commit": version.git_commit(),
        **app.config["INSTANCE_POLICY"].public_status().model_dump(mode="json"),
    }
