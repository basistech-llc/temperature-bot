"""Verify and stage an immutable Temperature Bot deployment package."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.deployment_package import (
    DeploymentManifest,
    extract_verified_package,
    verify_extracted_payload,
    verify_outer_checksum,
    verify_package,
)


class InstallationResult(BaseModel):
    """Machine-readable result of a verified package installation."""

    model_config = ConfigDict(extra="forbid")

    version: str
    commit: str
    release_directory: Path
    activated: bool
    host_configuration_installed: Literal[False] = False


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _install_environment(release: Path, manifest: DeploymentManifest, uv: str, python: str) -> None:
    environment = release / "venv"
    interpreter = environment / "bin/python"
    _run(uv, "venv", "--relocatable", "--python", python, str(environment))
    _run(
        uv,
        "pip",
        "sync",
        "--python",
        str(interpreter),
        "--require-hashes",
        str(release / manifest.requirements),
    )
    _run(
        uv,
        "pip",
        "install",
        "--python",
        str(interpreter),
        "--no-deps",
        str(release / manifest.wheel),
    )


def _verify_environment(release: Path, manifest: DeploymentManifest) -> None:
    environment = release / "venv"
    interpreter = environment / "bin/python"
    _run(
        str(interpreter),
        "-I",
        "-c",
        (
            "import importlib.util; from app.version import __version__; "
            f"assert __version__ == {manifest.version!r}, __version__; "
            "assert importlib.util.find_spec('bin.runner') is not None; "
            "assert importlib.util.find_spec('lib.ctools.clogging') is not None; "
            "assert importlib.util.find_spec('app.deployment_package') is not None"
        ),
    )
    _run(str(environment / "bin/gunicorn"), "--version")


def _activate(root: Path, release: Path) -> None:
    current = root / "current"
    if current.exists() and not current.is_symlink():
        raise ValueError(f"refusing to replace non-symlink activation path: {current}")
    temporary = root / f".current.{os.getpid()}"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(Path("releases") / release.name)
    os.replace(temporary, current)


def install_package(
    package: Path,
    root: Path,
    *,
    uv: str = "uv",
    python: str = "3.12",
    create_venv: bool = True,
    activate: bool = False,
) -> InstallationResult:
    """Stage a verified immutable release and optionally activate it."""
    manifest = verify_package(package)
    release_name = f"{manifest.version}-{manifest.commit[:12]}"
    releases = root / "releases"
    release = releases / release_name
    root.mkdir(parents=True, exist_ok=True)
    releases.mkdir(exist_ok=True)

    if release.exists():
        installed_manifest = DeploymentManifest.model_validate_json(
            (release / "manifest.json").read_bytes()
        )
        if installed_manifest != manifest:
            raise ValueError(f"installed release differs from package: {release}")
        verify_extracted_payload(release, installed_manifest)
    else:
        staging = releases / f".{release_name}.staging.{os.getpid()}"
        try:
            extract_verified_package(package, staging)
            if create_venv:
                _install_environment(staging, manifest, uv, python)
            os.replace(staging, release)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    if create_venv:
        _verify_environment(release, manifest)

    if activate:
        _activate(root, release)
    return InstallationResult(
        version=manifest.version,
        commit=manifest.commit,
        release_directory=release,
        activated=activate,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--checksum", type=Path)
    parser.add_argument("--require-checksum", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--root", type=Path, default=Path("/opt/temperature-bot"))
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--python", default="3.12")
    parser.add_argument("--skip-venv", action="store_true")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args(argv)

    sidecar = args.checksum or args.package.with_suffix(args.package.suffix + ".sha256")
    if sidecar.exists():
        verify_outer_checksum(args.package, sidecar)
    elif args.require_checksum:
        raise SystemExit(f"required checksum file is missing: {sidecar}")

    manifest = verify_package(args.package)
    if args.verify_only:
        print(manifest.model_dump_json(indent=2))
        return
    result = install_package(
        args.package,
        args.root,
        uv=args.uv,
        python=args.python,
        create_venv=not args.skip_venv,
        activate=args.activate,
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
