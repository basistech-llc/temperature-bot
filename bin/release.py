#!/usr/bin/env python3
"""Cut a new release.

The single source of truth for the version number is the top-level ``VERSION``
file. This script bumps that number, keeps ``pyproject.toml`` in sync, stamps
the running ``Unreleased`` section of ``CHANGELOG.md`` into a dated ``v{version}``
release section, commits the result, and creates a ``vX.Y.Z`` git tag.

It deliberately does **not** push: tagging and pushing stay a separate, manual
step. All bump levels (patch/minor/major) route through here so any tooling we
hook into the release flow runs identically regardless of level.

Usage:
    python bin/release.py --patch        # 0.1.0 -> 0.1.1   (the common case)
    python bin/release.py --minor        # 0.1.0 -> 0.2.0
    python bin/release.py --major        # 0.1.0 -> 1.0.0
    python bin/release.py --patch --dry-run   # show the plan, change nothing
"""

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "VERSION"
PYPROJECT = REPO_ROOT / "pyproject.toml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
PYPROJECT_VERSION_RE = re.compile(r'^(version = ")\d+\.\d+\.\d+(")$', re.MULTILINE)


def fail(message: str) -> None:
    """Print an error and exit non-zero."""
    print(f"release: {message}", file=sys.stderr)
    raise SystemExit(1)


def git(*args: str) -> str:
    """Run a git command in the repo root and return its stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def current_version() -> tuple[int, int, int]:
    """Read the canonical (major, minor, patch) from the VERSION file."""
    match = VERSION_RE.match(VERSION_FILE.read_text(encoding="utf-8").strip())
    if not match:
        fail(f"{VERSION_FILE} does not contain a valid X.Y.Z version")
    assert match is not None  # narrow type for mypy after fail()/SystemExit
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump(version: tuple[int, int, int], level: str) -> tuple[int, int, int]:
    """Apply a SemVer bump of the given level."""
    major, minor, patch = version
    if level == "major":
        return major + 1, 0, 0
    if level == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def write_version_file(new: str) -> None:
    VERSION_FILE.write_text(f"{new}\n", encoding="utf-8")


def write_pyproject(new: str) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    updated, count = PYPROJECT_VERSION_RE.subn(rf"\g<1>{new}\g<2>", text, count=1)
    if count != 1:
        fail(f"could not find a version line to sync in {PYPROJECT}")
    PYPROJECT.write_text(updated, encoding="utf-8")


def stamp_changelog(new: str, date: str) -> None:
    """Rename the running ``Unreleased`` section to a dated ``v{new}`` release.

    A fresh empty ``Unreleased`` section is left at the top for the next cycle.
    ``date`` is the friendly ``DDMmmYY`` form used in the headings.
    """
    text = CHANGELOG.read_text(encoding="utf-8")

    if "## Unreleased\n" not in text:
        fail(f"could not find '## Unreleased' section in {CHANGELOG}")

    # Warn (don't block) when there is nothing to release.
    unreleased_body = text.split("## Unreleased\n", 1)[1].split("\n## ", 1)[0]
    if not unreleased_body.strip():
        print(
            "release: warning: Unreleased section is empty; releasing anyway",
            file=sys.stderr,
        )

    # The content under Unreleased becomes the body of the new dated release;
    # an empty Unreleased stays on top for the next cycle.
    text = text.replace(
        "## Unreleased\n",
        f"## Unreleased\n\n## v{new} ({date})\n",
        1,
    )
    CHANGELOG.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cut a new release.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--patch", action="store_const", const="patch", dest="level")
    group.add_argument("--minor", action="store_const", const="minor", dest="level")
    group.add_argument("--major", action="store_const", const="major", dest="level")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would happen without writing, committing, or tagging",
    )
    args = parser.parse_args()

    prev = ".".join(map(str, current_version()))
    new = ".".join(map(str, bump(current_version(), args.level)))
    date = datetime.date.today().strftime("%d%b%y")
    tag = f"v{new}"

    if git("tag", "--list", tag).strip():
        fail(f"tag {tag} already exists")

    print(f"Releasing {prev} -> {new} ({args.level})")

    if args.dry_run:
        print("dry-run: no files changed, no commit, no tag")
        return

    if git("status", "--porcelain").strip():
        fail("working tree is not clean; commit or stash changes first")

    write_version_file(new)
    write_pyproject(new)
    stamp_changelog(new, date)

    git("add", str(VERSION_FILE), str(PYPROJECT), str(CHANGELOG))
    git("commit", "-m", f"Release {tag}")
    git("tag", tag)

    print(f"Committed and tagged {tag}.")
    print(f"Review, then push with:  git push && git push origin {tag}")


if __name__ == "__main__":
    main()
