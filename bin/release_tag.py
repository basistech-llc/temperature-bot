"""Validate a release tag against the canonical project version."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from packaging.version import Version

from bin.check_project_metadata import project_version as project_version_text

REPO_ROOT = Path(__file__).resolve().parents[1]


def project_version() -> Version:
    """Return the canonical project version."""
    version_text = project_version_text(REPO_ROOT)
    version = Version(version_text)
    if str(version) != version_text:
        raise ValueError(f"project version is not canonical PEP 440: {version_text}")
    return version


def validate_tag(tag: str) -> Version:
    """Return the project version when *tag* denotes that same PEP 440 version."""
    version = project_version()
    tag_version = Version(tag.removeprefix("v"))
    if tag_version != version:
        raise ValueError(f"tag {tag} does not identify project version {version}")
    return version


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", nargs="?", default=os.getenv("GITHUB_REF_NAME"))
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    if not args.tag:
        raise SystemExit("release tag is required")
    try:
        version = validate_tag(args.tag)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    output = f"version={version}\nprerelease={str(version.is_prerelease).lower()}\n"
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as stream:
            stream.write(output)
    print(output, end="")


if __name__ == "__main__":
    main()
