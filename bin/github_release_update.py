"""Discover, verify, stage, and optionally activate a GitHub release."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, TypeVar

from packaging.version import Version
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.deployment_package import (
    DeploymentManifest,
    verify_extracted_payload,
    verify_outer_checksum,
    verify_package,
)
from bin.install_deployment_package import install_package

DEFAULT_REPOSITORY = "basistech-llc/temperature-bot"
DEFAULT_API = "https://api.github.com"
DEFAULT_MAX_BYTES = 500 * 1024 * 1024
PACKAGE_PREFIX = "temperature-bot-deployment-"
STATE_FILE = "release-update-state.json"
ModelT = TypeVar("ModelT", bound=BaseModel)


class ReleaseChannel(StrEnum):
    """GitHub Release selection policy."""

    STABLE = "stable"
    PRERELEASE = "prerelease"


class GitHubAsset(BaseModel):
    """One downloadable GitHub Release asset."""

    model_config = ConfigDict(extra="ignore")

    name: str
    browser_download_url: str
    size: int = Field(ge=0)


class GitHubRelease(BaseModel):
    """GitHub Release fields required by the updater."""

    model_config = ConfigDict(extra="ignore")

    tag_name: str
    html_url: str
    draft: bool
    prerelease: bool
    assets: list[GitHubAsset]


class GitObject(BaseModel):
    """A GitHub Git-data object reference."""

    model_config = ConfigDict(extra="ignore")

    sha: str
    type: Literal["commit", "tag"]


class GitReference(BaseModel):
    """A GitHub tag reference."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    git_object: GitObject = Field(alias="object")


class AnnotatedTag(BaseModel):
    """A GitHub annotated tag object."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    git_object: GitObject = Field(alias="object")


class HealthEndpoint(BaseModel):
    """One endpoint and expected deployment identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str
    instance: str


class DeploymentTarget(BaseModel):
    """Immutable application target and its runtime units."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    root: Path
    quiesce_units: tuple[str, ...]
    resume_units: tuple[str, ...]
    health: tuple[HealthEndpoint, ...]


class ActivationOptions(BaseModel):
    """Runtime controls used by the schema-neutral activation transaction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    require_root: bool = True
    systemctl: str = "systemctl"
    create_venv: bool = True
    health_timeout: float = Field(default=30, gt=0)


class UpdateOptions(BaseModel):
    """One release-discovery and installation request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str = DEFAULT_REPOSITORY
    channel: ReleaseChannel = ReleaseChannel.STABLE
    api_base: str = DEFAULT_API
    check_only: bool = False
    activate: bool = False
    create_venv: bool = True


TARGETS = {
    "production": DeploymentTarget(
        name="production",
        root=Path("/opt/temperature-bot"),
        quiesce_units=(
            "temperature-bot-minute.timer",
            "temperature-bot-hourly.timer",
            "temperature-bot-daily.timer",
            "temperature-bot-performance-monitor.timer",
            "temperature-bot-minute.service",
            "temperature-bot-hourly.service",
            "temperature-bot-daily.service",
            "temperature-bot-performance-monitor.service",
            "temperature-bot-ae200-notifications.service",
            "air_basistech_net.service",
        ),
        resume_units=(
            "air_basistech_net.service",
            "temperature-bot-ae200-notifications.service",
            "temperature-bot-minute.timer",
            "temperature-bot-hourly.timer",
            "temperature-bot-daily.timer",
            "temperature-bot-performance-monitor.timer",
        ),
        health=(
            HealthEndpoint(
                url="http://127.0.0.1:8100/api/v1/version", instance="production"
            ),
        ),
    ),
    "staging": DeploymentTarget(
        name="staging",
        root=Path("/opt/temperature-bot-stage"),
        quiesce_units=(
            "temperature-bot-stage-minute.timer",
            "temperature-bot-stage-minute.service",
            "temperature-bot-stage-ae200-notifications.service",
            "air-stage_basistech_net.service",
        ),
        resume_units=(
            "air-stage_basistech_net.service",
            "temperature-bot-stage-ae200-notifications.service",
            "temperature-bot-stage-minute.timer",
        ),
        health=(
            HealthEndpoint(
                url="http://127.0.0.1:8101/api/v1/version", instance="air-stage"
            ),
        ),
    ),
    "developers": DeploymentTarget(
        name="developers",
        root=Path("/opt/temperature-bot-dev"),
        quiesce_units=(
            "slg1_basistech_net.socket",
            "deg1_basistech_net.socket",
            "slg1_basistech_net.service",
            "deg1_basistech_net.service",
        ),
        resume_units=(
            "slg1_basistech_net.socket",
            "deg1_basistech_net.socket",
            "slg1_basistech_net.service",
            "deg1_basistech_net.service",
        ),
        health=(
            HealthEndpoint(url="http://127.0.0.1:8003/api/v1/version", instance="slg1"),
            HealthEndpoint(url="http://127.0.0.1:8004/api/v1/version", instance="deg1"),
        ),
    ),
}


class UpdateResult(BaseModel):
    """Machine-readable updater outcome."""

    model_config = ConfigDict(extra="forbid")

    checked_at: datetime
    target: str
    release_url: str
    tag: str
    version: str
    commit: str
    disposition: Literal["current", "available", "staged", "activated"]
    release_directory: Path | None = None


def _request(url: str, *, timeout: float) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "temperature-bot-release-updater/1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.URLError as error:
        raise RuntimeError(f"GitHub request failed for {url}: {error}") from error


def _json(url: str, model: type[ModelT], *, timeout: float) -> ModelT:
    with _request(url, timeout=timeout) as response:
        return model.model_validate_json(response.read())


def discover_release(
    repository: str,
    channel: ReleaseChannel,
    *,
    api_base: str = DEFAULT_API,
    timeout: float = 15,
) -> GitHubRelease:
    """Return the newest non-draft release permitted by *channel*."""
    encoded_repo = urllib.parse.quote(repository, safe="/")
    base = f"{api_base.rstrip('/')}/repos/{encoded_repo}/releases"
    if channel is ReleaseChannel.STABLE:
        return _json(f"{base}/latest", GitHubRelease, timeout=timeout)
    with _request(f"{base}?per_page=30", timeout=timeout) as response:
        releases = TypeAdapter(list[GitHubRelease]).validate_json(response.read())
    try:
        return next(release for release in releases if not release.draft)
    except StopIteration as error:
        raise ValueError("GitHub has no published releases") from error


def resolve_tag_commit(
    repository: str,
    tag: str,
    *,
    api_base: str = DEFAULT_API,
    timeout: float = 15,
) -> str:
    """Resolve lightweight or annotated *tag* to its immutable commit."""
    encoded_repo = urllib.parse.quote(repository, safe="/")
    encoded_tag = urllib.parse.quote(tag, safe="")
    base = f"{api_base.rstrip('/')}/repos/{encoded_repo}/git"
    reference = _json(f"{base}/ref/tags/{encoded_tag}", GitReference, timeout=timeout)
    git_object = reference.git_object
    for _unused in range(4):
        if git_object.type == "commit":
            return git_object.sha
        annotated = _json(f"{base}/tags/{git_object.sha}", AnnotatedTag, timeout=timeout)
        git_object = annotated.git_object
    raise ValueError(f"tag {tag} has excessive annotated-tag indirection")


def _release_assets(release: GitHubRelease) -> tuple[GitHubAsset, GitHubAsset]:
    packages = [
        asset
        for asset in release.assets
        if asset.name.startswith(PACKAGE_PREFIX) and asset.name.endswith(".zip")
    ]
    if len(packages) != 1:
        raise ValueError(f"release must contain exactly one deployment ZIP; found {len(packages)}")
    package = packages[0]
    checksums = [asset for asset in release.assets if asset.name == f"{package.name}.sha256"]
    if len(checksums) != 1:
        raise ValueError("release must contain the deployment ZIP checksum sidecar")
    return package, checksums[0]


def _download(asset: GitHubAsset, destination: Path, *, max_bytes: int, timeout: float) -> None:
    if asset.size > max_bytes:
        raise ValueError(f"release asset exceeds size limit: {asset.name}")
    total = 0
    with _request(asset.browser_download_url, timeout=timeout) as response:
        with destination.open("xb") as output:
            while block := response.read(min(1024 * 1024, max_bytes - total + 1)):
                total += len(block)
                if total > max_bytes:
                    raise ValueError(f"release asset exceeds size limit: {asset.name}")
                output.write(block)
    if total != asset.size:
        raise ValueError(
            f"release asset size mismatch for {asset.name}: expected {asset.size}, got {total}"
        )


def download_and_verify(
    release: GitHubRelease,
    expected_commit: str,
    directory: Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = 60,
) -> tuple[Path, DeploymentManifest]:
    """Download and verify the release package, checksum, tag, and commit."""
    package_asset, checksum_asset = _release_assets(release)
    package = directory / package_asset.name
    checksum = directory / checksum_asset.name
    _download(package_asset, package, max_bytes=max_bytes, timeout=timeout)
    _download(checksum_asset, checksum, max_bytes=1024 * 1024, timeout=timeout)
    verify_outer_checksum(package, checksum)
    manifest = verify_package(package)
    if manifest.dirty:
        raise ValueError("release package was built from a dirty source tree")
    if Version(release.tag_name.removeprefix("v")) != Version(manifest.version):
        raise ValueError(
            f"release tag {release.tag_name} does not match package version {manifest.version}"
        )
    if manifest.commit != expected_commit:
        raise ValueError(
            f"release tag commit {expected_commit} does not match package commit {manifest.commit}"
        )
    return package, manifest


def active_manifest(target: DeploymentTarget) -> DeploymentManifest | None:
    """Return the verified active manifest, when the target is initialized."""
    manifest_path = target.root / "current/manifest.json"
    if not manifest_path.exists():
        return None
    manifest = DeploymentManifest.model_validate_json(manifest_path.read_bytes())
    verify_extracted_payload(manifest_path.parent, manifest)
    return manifest


def update_required(active: DeploymentManifest | None, candidate: DeploymentManifest) -> bool:
    """Return whether *candidate* is newer than the active release."""
    if active is None:
        return True
    if active.commit == candidate.commit and Version(active.version) == Version(candidate.version):
        return False
    if Version(candidate.version) <= Version(active.version):
        raise ValueError(
            f"refusing non-newer release {candidate.version} over active {active.version}"
        )
    return True


def migration_fingerprint(manifest: DeploymentManifest) -> dict[str, str]:
    """Return version-matched migration hashes from a manifest."""
    migrations = set(manifest.migrations)
    return {item.path: item.sha256 for item in manifest.files if item.path in migrations}


def activation_is_schema_neutral(
    active: DeploymentManifest | None, candidate: DeploymentManifest
) -> bool:
    """Return whether activation can avoid every database migration."""
    return active is not None and migration_fingerprint(active) == migration_fingerprint(candidate)


def _is_active(unit: str, systemctl: str = "systemctl") -> bool:
    result = subprocess.run(
        [systemctl, "is-active", "--quiet", unit], check=False, timeout=10
    )
    return result.returncode == 0


def _systemctl(action: str, unit: str, systemctl: str = "systemctl") -> None:
    subprocess.run([systemctl, action, unit], check=True, timeout=60)


def _switch_current(root: Path, release: Path) -> None:
    current = root / "current"
    temporary = root / f".current.{os.getpid()}"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(Path("releases") / release.name)
    os.replace(temporary, current)


def _check_health(
    target: DeploymentTarget, manifest: DeploymentManifest, *, timeout: float = 30
) -> None:
    deadline = time.monotonic() + timeout
    errors: list[str] = []
    while time.monotonic() < deadline:
        errors.clear()
        for endpoint in target.health:
            try:
                with urllib.request.urlopen(endpoint.url, timeout=3) as response:
                    payload: dict[str, Any] = json.load(response)
                if payload.get("version") != manifest.version:
                    raise ValueError(f"version is {payload.get('version')}")
                if payload.get("commit") != manifest.commit:
                    raise ValueError(f"commit is {payload.get('commit')}")
                if payload.get("instance") != endpoint.instance:
                    raise ValueError(f"instance is {payload.get('instance')}")
            except (OSError, ValueError, json.JSONDecodeError) as error:
                errors.append(f"{endpoint.url}: {error}")
        if not errors:
            return
        time.sleep(1)
    raise RuntimeError("release health checks failed: " + "; ".join(errors))


def activate_schema_neutral_release(
    package: Path,
    target: DeploymentTarget,
    active: DeploymentManifest | None,
    candidate: DeploymentManifest,
    options: ActivationOptions = ActivationOptions(),
) -> Path:
    """Activate with systemd rollback only when no database change is possible."""
    if options.require_root and os.geteuid() != 0:
        raise PermissionError("release activation must run as root")
    if not activation_is_schema_neutral(active, candidate):
        raise ValueError(
            "candidate migrations differ from the active release; stage succeeded but "
            "activation requires the transactional migration workflow in issue #216"
        )
    old_release = (target.root / "current").resolve(strict=True)
    was_active = {
        unit: _is_active(unit, options.systemctl) for unit in target.resume_units
    }
    try:
        for unit in target.quiesce_units:
            if _is_active(unit, options.systemctl):
                _systemctl("stop", unit, options.systemctl)
        installation = install_package(
            package,
            target.root,
            create_venv=options.create_venv,
            activate=True,
        )
        for unit in target.resume_units:
            if was_active.get(unit):
                _systemctl("start", unit, options.systemctl)
        _check_health(target, candidate, timeout=options.health_timeout)
        return installation.release_directory
    except Exception:
        for unit in target.resume_units:
            if _is_active(unit, options.systemctl):
                _systemctl("stop", unit, options.systemctl)
        _switch_current(target.root, old_release)
        for unit in target.resume_units:
            if was_active.get(unit):
                _systemctl("start", unit, options.systemctl)
        raise


def _write_state(target: DeploymentTarget, result: UpdateResult) -> None:
    target.root.mkdir(parents=True, exist_ok=True)
    destination = target.root / STATE_FILE
    with tempfile.NamedTemporaryFile("w", dir=target.root, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(result.model_dump_json(indent=2) + "\n")
    try:
        temporary.chmod(0o640)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def run_update(
    target: DeploymentTarget, options: UpdateOptions = UpdateOptions()
) -> UpdateResult:
    """Run one serialized release check for *target*."""
    release = discover_release(
        options.repository, options.channel, api_base=options.api_base
    )
    expected_commit = resolve_tag_commit(
        options.repository, release.tag_name, api_base=options.api_base
    )
    active = active_manifest(target)
    if active and active.commit == expected_commit:
        return UpdateResult(
            checked_at=datetime.now(timezone.utc),
            target=target.name,
            release_url=release.html_url,
            tag=release.tag_name,
            version=active.version,
            commit=active.commit,
            disposition="current",
            release_directory=(target.root / "current").resolve(),
        )
    with tempfile.TemporaryDirectory(prefix="temperature-bot-release-") as temporary:
        package, manifest = download_and_verify(
            release, expected_commit, Path(temporary)
        )
        update_required(active, manifest)
        disposition: Literal["available", "staged", "activated"] = "available"
        release_directory = None
        if not options.check_only:
            target.root.mkdir(parents=True, exist_ok=True)
            with (target.root / ".release-update.lock").open("a+b") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                installation = install_package(
                    package,
                    target.root,
                    create_venv=options.create_venv,
                    activate=False,
                )
                disposition = "staged"
                release_directory = installation.release_directory
                if options.activate:
                    if not activation_is_schema_neutral(active, manifest):
                        staged = UpdateResult(
                            checked_at=datetime.now(timezone.utc),
                            target=target.name,
                            release_url=release.html_url,
                            tag=release.tag_name,
                            version=manifest.version,
                            commit=manifest.commit,
                            disposition="staged",
                            release_directory=release_directory,
                        )
                        _write_state(target, staged)
                        raise ValueError(
                            "candidate migrations differ from the active release; "
                            "release was staged but activation requires issue #216"
                        )
                    release_directory = activate_schema_neutral_release(
                        package, target, active, manifest
                    )
                    disposition = "activated"
        result = UpdateResult(
            checked_at=datetime.now(timezone.utc),
            target=target.name,
            release_url=release.html_url,
            tag=release.tag_name,
            version=manifest.version,
            commit=manifest.commit,
            disposition=disposition,
            release_directory=release_directory,
        )
        if not options.check_only:
            _write_state(target, result)
        return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument(
        "--channel",
        type=ReleaseChannel,
        choices=ReleaseChannel,
        default=ReleaseChannel.STABLE,
    )
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args(argv)
    if args.activate and args.check_only:
        parser.error("--activate cannot be combined with --check-only")
    try:
        result = run_update(
            TARGETS[args.target],
            UpdateOptions(
                repository=args.repository,
                channel=args.channel,
                check_only=args.check_only,
                activate=args.activate,
            ),
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
