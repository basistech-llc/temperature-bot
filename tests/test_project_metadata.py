"""Tests for the pre-install project metadata check."""

from pathlib import Path

import pytest

from bin.check_project_metadata import project_version


def write_metadata(repo_root: Path, version: str, configured_version: str) -> None:
    """Write minimal version metadata under *repo_root*."""
    (repo_root / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    (repo_root / "pyproject.toml").write_text(
        f'[project]\nversion = "{configured_version}"\n', encoding="utf-8"
    )


def test_project_version_accepts_matching_metadata(tmp_path: Path) -> None:
    write_metadata(tmp_path, "1.2.3.dev1", "1.2.3.dev1")
    assert project_version(tmp_path) == "1.2.3.dev1"


def test_project_version_rejects_mismatched_metadata(tmp_path: Path) -> None:
    write_metadata(tmp_path, "1.2.3.dev1", "1.2.dev1")
    with pytest.raises(ValueError, match="VERSION .* does not match pyproject.toml"):
        project_version(tmp_path)
