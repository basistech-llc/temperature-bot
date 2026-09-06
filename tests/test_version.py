"""Tests for version metadata."""

import json

import subprocess

from conftest import flask_test_client  # noqa: F401  # pylint: disable=unused-import

from app import version
from app.main import app
from bin.check_project_metadata import project_version


def test_installed_version_comes_from_project_metadata():
    assert version.__version__ == project_version()


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


def test_immutable_manifest_overrides_stale_environment(monkeypatch, tmp_path):
    commit = "a" * 40
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "application": "temperature-bot",
                "version": version.__version__,
                "commit": commit,
                "dirty": False,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_COMMIT", "b" * 40)
    version.git_commit.cache_clear()
    version.git_sha.cache_clear()
    try:
        assert version.git_commit() == commit
        assert version.git_sha() == commit[:12]
    finally:
        version.git_commit.cache_clear()
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
