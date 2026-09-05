"""Build a deployment package from an immutable GitHub source selection."""

from __future__ import annotations

import os
import pwd
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.deployment_package import (
    DeploymentManifest,
    verify_outer_checksum,
    verify_package,
)
from bin.build_deployment_package import (
    CheckoutPackageOptions,
    build_checkout_package,
)

DEFAULT_BUILD_USER = "nobody"
DEFAULT_FLYWAY_VERSION = "12.8.1"


class SourceSelection(BaseModel):
    """One mutable or immutable source selector resolved to a commit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["branch", "commit"]
    value: str
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    html_url: str


class SourceBuildOptions(BaseModel):
    """Trusted host inputs for one unprivileged source build."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str
    clone_url: str | None = None
    uv: str
    python: str
    build_user: str = DEFAULT_BUILD_USER
    flyway_version: str = DEFAULT_FLYWAY_VERSION


class BuilderContext(BaseModel):
    """Minimal identity and environment passed to build subprocesses."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    cwd: Path
    environment: dict[str, str]
    uid: int
    gid: int


def _trusted_root_executable(value: str) -> Path:
    executable = Path(value).resolve(strict=True)
    metadata = executable.stat()
    if not stat.S_ISREG(metadata.st_mode) or not os.access(executable, os.X_OK):
        raise ValueError(f"required executable is not a regular executable: {executable}")
    if metadata.st_uid != 0 or metadata.st_mode & 0o022:
        raise ValueError(
            f"required executable must be root-owned and not group/world-writable: {executable}"
        )
    return executable


def _run_builder(
    args: list[str], context: BuilderContext, *, capture_output: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run one source operation without root or supplementary groups."""
    kwargs: dict[str, Any] = {
        "cwd": context.cwd,
        "env": context.environment,
        "text": True,
        "capture_output": capture_output,
        "timeout": 600,
    }
    if os.geteuid() == 0:
        kwargs.update(
            user=context.uid,
            group=context.gid,
            extra_groups=(),
            umask=0o077,
        )
    elif os.geteuid() != context.uid:
        raise PermissionError("source build must run as root or as the selected builder")
    return subprocess.run(args, check=True, **kwargs)


def _prepare_workspace(
    directory: Path, options: SourceBuildOptions
) -> tuple[Path, Path, Path, BuilderContext]:
    try:
        builder = pwd.getpwnam(options.build_user)
    except KeyError as error:
        raise ValueError(
            f"source build user does not exist: {options.build_user}"
        ) from error
    if builder.pw_uid == 0:
        raise ValueError("source build user must not be root")
    if os.geteuid() == 0:
        os.chown(directory, builder.pw_uid, builder.pw_gid)
        directory.chmod(0o700)

    workspace = directory / "source-build"
    home = workspace / "home"
    artifacts = workspace / "artifacts"
    workspace.mkdir(mode=0o700)
    for path in (workspace, home, artifacts):
        if path is not workspace:
            path.mkdir(mode=0o700)
        if os.geteuid() == 0:
            os.chown(path, builder.pw_uid, builder.pw_gid)
    uv_path = (
        _trusted_root_executable(options.uv)
        if os.geteuid() == 0
        else Path(options.uv).resolve(strict=True)
    )
    environment = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_LFS_SKIP_SMUDGE": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": f"{uv_path.parent}:/usr/bin:/bin",
        "UV_CACHE_DIR": str(workspace / "uv-cache"),
        "UV_NO_MODIFY_PATH": "1",
        "UV_PYTHON": options.python,
    }
    return workspace, artifacts, uv_path, BuilderContext(
        cwd=workspace,
        environment=environment,
        uid=builder.pw_uid,
        gid=builder.pw_gid,
    )


def _checkout_source(
    selection: SourceSelection,
    options: SourceBuildOptions,
    workspace: Path,
    context: BuilderContext,
) -> tuple[Path, datetime]:
    checkout = workspace / "checkout"
    clone_url = options.clone_url or f"https://github.com/{options.repository}.git"
    _run_builder(
        [
            "/usr/bin/git",
            "clone",
            "--no-checkout",
            "--filter=blob:none",
            "--config",
            "core.hooksPath=/dev/null",
            clone_url,
            str(checkout),
        ],
        context,
    )
    _run_builder(
        ["/usr/bin/git", "-C", str(checkout), "checkout", "--detach", selection.commit],
        context,
    )
    head = _run_builder(
        ["/usr/bin/git", "-C", str(checkout), "rev-parse", "HEAD"],
        context,
        capture_output=True,
    ).stdout.strip()
    status = _run_builder(
        ["/usr/bin/git", "-C", str(checkout), "status", "--porcelain"],
        context,
        capture_output=True,
    ).stdout.strip()
    if head != selection.commit:
        raise ValueError(
            f"source checkout commit {head} does not match selected commit {selection.commit}"
        )
    if status:
        raise ValueError("source checkout is dirty before build")
    commit_epoch = _run_builder(
        ["/usr/bin/git", "-C", str(checkout), "show", "-s", "--format=%ct", "HEAD"],
        context,
        capture_output=True,
    ).stdout.strip()
    return checkout, datetime.fromtimestamp(int(commit_epoch), timezone.utc)


def _build_inputs(
    checkout: Path,
    artifacts: Path,
    uv_path: Path,
    context: BuilderContext,
) -> tuple[Path, Path]:
    dist = artifacts / "dist"
    requirements = artifacts / "runtime.txt"
    build_context = context.model_copy(update={"cwd": checkout})
    _run_builder(
        [str(uv_path), "build", "--no-sources", "--out-dir", str(dist)],
        build_context,
    )
    exported = _run_builder(
        [
            str(uv_path),
            "export",
            "--quiet",
            "--locked",
            "--no-dev",
            "--no-editable",
            "--no-emit-project",
        ],
        build_context,
        capture_output=True,
    )
    requirements.write_text(exported.stdout, encoding="utf-8")
    version = (checkout / "VERSION").read_text(encoding="utf-8").strip()
    wheels = sorted(dist.glob(f"temperature_bot-{version}-*.whl"))
    if len(wheels) != 1:
        raise ValueError(f"expected one source wheel for {version}; found {len(wheels)}")
    return requirements, wheels[0]


def build_source_package(
    selection: SourceSelection,
    directory: Path,
    options: SourceBuildOptions,
) -> tuple[Path, DeploymentManifest]:
    """Build a selected commit unprivileged, then verify its deployment package."""
    workspace, artifacts, uv_path, context = _prepare_workspace(directory, options)
    checkout, built_at = _checkout_source(selection, options, workspace, context)
    reproducible_context = context.model_copy(
        update={
            "environment": {
                **context.environment,
                "SOURCE_DATE_EPOCH": str(int(built_at.timestamp())),
            }
        }
    )
    requirements, wheel = _build_inputs(
        checkout, artifacts, uv_path, reproducible_context
    )
    if os.geteuid() == 0:
        os.chown(directory, 0, 0)
        directory.chmod(0o700)
    package = build_checkout_package(
        checkout,
        directory,
        requirements,
        wheel,
        CheckoutPackageOptions(
            flyway_version=options.flyway_version,
            commit=selection.commit,
            built_at=built_at,
            dirty=False,
        ),
    )
    verify_outer_checksum(package)
    manifest = verify_package(package)
    if manifest.dirty or manifest.commit != selection.commit:
        raise ValueError("source package provenance does not match the selected commit")
    return package, manifest
