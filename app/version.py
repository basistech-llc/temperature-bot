"""Application version helpers.

The single source of truth for the version *number* is the top-level ``VERSION``
file (one line, e.g. ``0.1.0``). It lives outside ``app/constants.py`` so that
routine version bumps don't churn that file and bury real constant changes.

This module reads ``VERSION`` once at import and augments it with the deployed
git revision (short SHA) for traceability: production deploys via ``git pull``
and keeps a working ``.git``, so the running commit can be reported in the UI
and API.
"""

import functools
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

__version__ = (_REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


@functools.lru_cache(maxsize=1)
def git_sha() -> str | None:
    """Return the short git SHA of the deployed commit, or None if unavailable.

    Cached for the life of the process: the checked-out revision cannot change
    while the app is running, and we never want to fork git per request.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def display_version() -> str:
    """Human-facing version string, e.g. ``v0.1.0 (git sha: abc1234)``.

    Falls back to the bare version when no git SHA is available (e.g. a deploy
    without a ``.git`` directory).
    """
    sha = git_sha()
    return f"v{__version__} (git sha: {sha})" if sha else f"v{__version__}"
