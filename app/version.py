"""Application version helpers.

The top-level VERSION file is the source of truth for the version number. Git
metadata is reported separately so the UI and API can show what checkout is
deployed without mixing that into the semantic version string.
"""

import functools
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "VERSION"
UNKNOWN_SHA = "unknown"

__version__ = VERSION_FILE.read_text(encoding="utf-8").strip()


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
    env_commit = os.getenv("GIT_COMMIT") or os.getenv("COMMIT_SHA")
    if env_commit:
        return env_commit[:12]
    return _git_rev_parse("--short=12", "HEAD")


@functools.lru_cache(maxsize=1)
def git_branch() -> str:
    """Return the current git branch for this checkout, or "unknown"."""
    env_branch = os.getenv("GIT_BRANCH") or os.getenv("BRANCH_NAME")
    if env_branch:
        return env_branch.removeprefix("origin/")
    return _git_rev_parse("--abbrev-ref", "HEAD")
