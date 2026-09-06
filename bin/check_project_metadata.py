"""Verify that the project's independently stored versions agree."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_KEY = "project"
VERSION_KEY = "version"


def project_version(repo_root: Path = REPO_ROOT) -> str:
    """Return the version when VERSION and pyproject.toml agree."""
    version = (repo_root / "VERSION").read_text(encoding="utf-8").strip()
    pyproject = tomllib.loads(
        (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    )
    configured_version = pyproject[PROJECT_KEY][VERSION_KEY]
    if configured_version != version:
        raise ValueError(
            f"VERSION ({version}) does not match pyproject.toml ({configured_version})"
        )
    return version


def main() -> None:
    """Report the matching project version or exit with a useful error."""
    try:
        version = project_version()
    except (KeyError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(f"Project metadata agrees on version {version}")


if __name__ == "__main__":
    main()
