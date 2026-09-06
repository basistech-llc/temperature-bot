"""Read the canonical project metadata from pyproject.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_KEY = "project"
VERSION_KEY = "version"
REQUIRES_PYTHON_KEY = "requires-python"


def project_field(field: str, repo_root: Path = REPO_ROOT) -> str:
    """Return one required string field from ``[project]``."""
    path = repo_root / "pyproject.toml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"cannot read {path}: {error}") from error
    try:
        pyproject = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"invalid TOML in {path}: {error}") from error
    try:
        project = pyproject[PROJECT_KEY]
    except KeyError as error:
        raise ValueError(f"{path} is missing [project]") from error
    if not isinstance(project, dict):
        raise ValueError(f"{path} [project] must be a table")
    try:
        value = project[field]
    except KeyError as error:
        raise ValueError(f"{path} is missing [project].{field}") from error
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} [project].{field} must be a nonempty string")
    return value


def project_version(repo_root: Path = REPO_ROOT) -> str:
    """Return the sole source-coded project version."""
    return project_field(VERSION_KEY, repo_root)


def project_requires_python(repo_root: Path = REPO_ROOT) -> str:
    """Return the project's Python compatibility constraint."""
    return project_field(REQUIRES_PYTHON_KEY, repo_root)


def main() -> None:
    """Report the canonical project version or exit with a useful error."""
    try:
        version = project_version()
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(f"Project version: {version} (pyproject.toml)")


if __name__ == "__main__":
    main()
