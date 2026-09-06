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
from bin.check_project_metadata import project_version

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


class BuildOutputContext(BaseModel):
    """Anchored untrusted output and private trusted destination."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifacts: Path
    artifacts_fd: int
    trusted: Path


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
        os.chown(directory, 0, 0)
    directory.chmod(0o711)

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


def _freeze_checkout(checkout: Path) -> None:
    """Make every selected source byte immutable before candidate code runs."""
    paths = [checkout, *checkout.rglob("*")]
    if any(path.is_symlink() for path in paths):
        raise ValueError("source checkout contains a symbolic link")
    for path in reversed(paths):
        metadata = path.stat()
        if os.geteuid() == 0:
            os.chown(path, 0, 0)
        path.chmod(0o555 if path.is_dir() or metadata.st_mode & 0o111 else 0o444)


def _restore_cleanup_access(directory: Path, checkout: Path) -> None:
    """Keep the completed source private while permitting temporary cleanup."""
    for path in checkout.rglob("*"):
        if path.is_dir():
            path.chmod(0o700)
    checkout.chmod(0o700)
    directory.chmod(0o700)


def _build_inputs(
    checkout: Path,
    output: BuildOutputContext,
    uv_path: Path,
    context: BuilderContext,
) -> tuple[Path, Path]:
    dist = output.artifacts / "dist"
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
    requirements = output.trusted / "runtime.txt"
    _write_trusted_output(requirements, exported.stdout.encode("utf-8"))
    version = project_version(checkout)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    dist_fd = os.open("dist", directory_flags, dir_fd=output.artifacts_fd)
    try:
        wheel_names = sorted(
            name
            for name in os.listdir(dist_fd)
            if name.startswith(f"temperature_bot-{version}-") and name.endswith(".whl")
        )
        if len(wheel_names) != 1:
            raise ValueError(
                f"expected one source wheel for {version}; found {len(wheel_names)}"
            )
        wheel = output.trusted / wheel_names[0]
        _copy_builder_output(dist_fd, wheel_names[0], wheel, context.uid)
    finally:
        os.close(dist_fd)
    return requirements, wheel


def _write_trusted_output(destination: Path, data: bytes) -> None:
    descriptor = os.open(
        destination,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0),
        0o400,
    )
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(descriptor, view) :]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy_builder_output(
    directory_fd: int, name: str, destination: Path, expected_uid: int
) -> None:
    """Copy one stable regular builder output into root-owned storage."""
    source_fd = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=directory_fd,
    )
    destination_fd: int | None = None
    try:
        before = os.fstat(source_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != expected_uid
        ):
            raise ValueError(f"untrusted builder output is not a private regular file: {name}")
        destination_fd = os.open(
            destination,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o400,
        )
        while block := os.read(source_fd, 1024 * 1024):
            view = memoryview(block)
            while view:
                view = view[os.write(destination_fd, view) :]
        os.fsync(destination_fd)
        after = os.fstat(source_fd)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if before_identity != after_identity:
            raise ValueError(f"builder output changed while being copied: {name}")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        if destination_fd is not None:
            os.close(destination_fd)
        os.close(source_fd)


def build_source_package(
    selection: SourceSelection,
    directory: Path,
    options: SourceBuildOptions,
) -> tuple[Path, DeploymentManifest]:
    """Build a selected commit unprivileged, then verify its deployment package."""
    _workspace, artifacts, uv_path, context = _prepare_workspace(directory, options)
    trusted = directory / "trusted"
    trusted.mkdir(mode=0o700)
    artifacts_fd = os.open(
        artifacts,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
    )
    trusted_context = context.model_copy(
        update={
            "cwd": directory,
            "environment": {**context.environment, "HOME": str(directory)},
            "uid": os.geteuid(),
            "gid": os.getegid(),
        }
    )
    checkout, built_at = _checkout_source(
        selection, options, directory, trusted_context
    )
    _freeze_checkout(checkout)
    try:
        reproducible_context = context.model_copy(
            update={
                "cwd": checkout,
                "environment": {
                    **context.environment,
                    "SOURCE_DATE_EPOCH": str(int(built_at.timestamp())),
                },
            }
        )
        requirements, wheel = _build_inputs(
            checkout,
            BuildOutputContext(
                artifacts=artifacts,
                artifacts_fd=artifacts_fd,
                trusted=trusted,
            ),
            uv_path,
            reproducible_context,
        )
        package = build_checkout_package(
            checkout,
            trusted,
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
    finally:
        os.close(artifacts_fd)
        _restore_cleanup_access(directory, checkout)
