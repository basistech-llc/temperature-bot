"""Application version helpers.

The top-level VERSION file is the source of truth for the version number. Git
metadata is reported separately so the UI and API can show what checkout is
deployed without mixing that into the semantic version string.
"""

import functools
import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "VERSION"
UNKNOWN_SHA = "unknown"

__version__ = VERSION_FILE.read_text(encoding="utf-8").strip()


def _deployment_commit() -> str | None:
    """Return provenance from an immutable release manifest, when present."""
    manifest_path = Path.cwd() / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        manifest.get("application") == "temperature-bot"
        and manifest.get("version") == __version__
        and manifest.get("dirty") is False
    ):
        commit = manifest.get("commit")
        if isinstance(commit, str):
            return commit
    return None


def _git_rev_parse(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return UNKNOWN_SHA
    return result.stdout.strip() or UNKNOWN_SHA


@functools.lru_cache(maxsize=1)
def git_sha() -> str:
    """Return the short git SHA for this checkout, or "unknown"."""
    deployed = _deployment_commit()
    if deployed:
        return deployed[:12]
    env_commit = os.getenv("GIT_COMMIT") or os.getenv("COMMIT_SHA")
    if env_commit:
        return env_commit[:12]
    return _git_rev_parse("--short=12", "HEAD")


@functools.lru_cache(maxsize=1)
def git_commit() -> str:
    """Return the exact deployed commit, or ``unknown``."""
    deployed = _deployment_commit()
    if deployed:
        return deployed
    env_commit = os.getenv("GIT_COMMIT") or os.getenv("COMMIT_SHA")
    if env_commit:
        return env_commit
    return _git_rev_parse("HEAD")


@functools.lru_cache(maxsize=1)
def git_branch() -> str:
    """Return the current git branch for this checkout, or "unknown"."""
    env_branch = os.getenv("GIT_BRANCH") or os.getenv("BRANCH_NAME")
    if env_branch:
        return env_branch.removeprefix("origin/")
    return _git_rev_parse("--abbrev-ref", "HEAD")
