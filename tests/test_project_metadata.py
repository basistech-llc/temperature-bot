"""Tests for canonical project metadata."""

from pathlib import Path

import pytest

from bin.check_project_metadata import project_version


def write_metadata(repo_root: Path, version: str) -> None:
    """Write minimal project metadata under *repo_root*."""
    (repo_root / "pyproject.toml").write_text(
        f'[project]\nversion = "{version}"\n', encoding="utf-8"
    )


def test_project_version_reads_pyproject(tmp_path: Path) -> None:
    write_metadata(tmp_path, "1.2.3.dev1")
    assert project_version(tmp_path) == "1.2.3.dev1"


def test_project_version_rejects_empty_metadata(tmp_path: Path) -> None:
    write_metadata(tmp_path, "")
    with pytest.raises(ValueError, match="must be a nonempty string"):
        project_version(tmp_path)
