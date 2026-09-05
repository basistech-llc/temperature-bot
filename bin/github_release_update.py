"""Discover, verify, stage, and optionally activate a GitHub release."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
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

from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.deployment_package import (
    DeploymentManifest,
    verify_extracted_payload,
    verify_outer_checksum,
    verify_package,
)
from bin.install_deployment_package import install_package
from bin.source_deployment import (
    DEFAULT_BUILD_USER,
    SourceBuildOptions,
    SourceSelection,
    build_source_package,
)

DEFAULT_REPOSITORY = "basistech-llc/temperature-bot"
DEFAULT_API = "https://api.github.com"
DEFAULT_MAX_BYTES = 500 * 1024 * 1024
DEFAULT_UV = "/usr/local/bin/uv"
RELEASES_PER_PAGE = 100
MAX_RELEASE_PAGES = 20
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


class GitHubCommit(BaseModel):
    """An immutable commit resolved by GitHub from a branch or SHA."""

    model_config = ConfigDict(extra="ignore")

    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    html_url: str


class HealthEndpoint(BaseModel):
    """One endpoint and expected deployment identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str
    instance: str
    control_mode: str | None = None


class RuntimeHealth(BaseModel):
    """Fields used to prove target identity and release health."""

    model_config = ConfigDict(extra="ignore")

    version: str
    commit: str
    instance: str
    control_mode: str | None = None


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
    uv: str = DEFAULT_UV
    python: str = "3.12"
    health_timeout: float = Field(default=30, gt=0)


class UpdateOptions(BaseModel):
    """One release-discovery and installation request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str = DEFAULT_REPOSITORY
    channel: ReleaseChannel = ReleaseChannel.STABLE
    api_base: str = DEFAULT_API
    tag: str | None = None
    branch: str | None = None
    commit: str | None = None
    check_only: bool = False
    activate: bool = False
    create_venv: bool = True
    uv: str = DEFAULT_UV
    python: str = "3.12"
    build_user: str = DEFAULT_BUILD_USER

    @model_validator(mode="after")
    def one_source_selector(self) -> "UpdateOptions":
        selectors = (self.tag, self.branch, self.commit)
        if sum(value is not None for value in selectors) > 1:
            raise ValueError("--tag, --branch, and --commit are mutually exclusive")
        return self


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
                url="http://127.0.0.1:8100/api/v1/version",
                instance="production",
                control_mode="live",
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
                url="http://127.0.0.1:8101/api/v1/version",
                instance="air-stage",
                control_mode="live",
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
            HealthEndpoint(
                url="http://127.0.0.1:8003/api/v1/version",
                instance="slg1",
                control_mode="simulator",
            ),
            HealthEndpoint(
                url="http://127.0.0.1:8004/api/v1/version",
                instance="deg1",
                control_mode="simulator",
            ),
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
    tag: str | None = None,
    timeout: float = 15,
) -> GitHubRelease:
    """Return an eligible application release permitted by *channel*."""
    encoded_repo = urllib.parse.quote(repository, safe="/")
    base = f"{api_base.rstrip('/')}/repos/{encoded_repo}/releases"
    if tag:
        encoded_tag = urllib.parse.quote(tag, safe="")
        release = _json(
            f"{base}/tags/{encoded_tag}", GitHubRelease, timeout=timeout
        )
        if not _eligible_release(release, channel):
            raise ValueError(f"release {tag} is not an eligible {channel.value} release")
        return release

    for page in range(1, MAX_RELEASE_PAGES + 1):
        url = f"{base}?per_page={RELEASES_PER_PAGE}&page={page}"
        with _request(url, timeout=timeout) as response:
            releases = TypeAdapter(list[GitHubRelease]).validate_json(response.read())
        for release in releases:
            if _eligible_release(release, channel):
                return release
        if len(releases) < RELEASES_PER_PAGE:
            break
    raise ValueError(f"GitHub has no eligible {channel.value} application release")


def _eligible_release(release: GitHubRelease, channel: ReleaseChannel) -> bool:
    """Return whether *release* is a publishable Temperature Bot artifact."""
    if release.draft:
        return False
    try:
        version = Version(release.tag_name.removeprefix("v"))
        _release_assets(release)
    except (InvalidVersion, ValueError):
        return False
    if channel is ReleaseChannel.STABLE:
        return not release.prerelease and not version.is_prerelease
    return True


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


def resolve_source_selection(
    repository: str,
    kind: Literal["branch", "commit"],
    value: str,
    *,
    api_base: str = DEFAULT_API,
    timeout: float = 15,
) -> SourceSelection:
    """Resolve a branch or commit selector to one immutable GitHub commit."""
    if not value or value.strip() != value:
        raise ValueError(f"invalid {kind} selector")
    if kind == "commit" and not re.fullmatch(r"[0-9a-fA-F]{7,40}", value):
        raise ValueError("commit must be a 7-to-40-character hexadecimal SHA")
    encoded_repo = urllib.parse.quote(repository, safe="/")
    encoded_value = urllib.parse.quote(value, safe="")
    record = _json(
        f"{api_base.rstrip('/')}/repos/{encoded_repo}/commits/{encoded_value}",
        GitHubCommit,
        timeout=timeout,
    )
    if kind == "commit" and not record.sha.startswith(value.lower()):
        raise ValueError(
            f"GitHub resolved commit {value} to unexpected SHA {record.sha}"
        )
    return SourceSelection(
        kind=kind,
        value=value,
        commit=record.sha,
        html_url=record.html_url,
    )


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


def update_required(
    active: DeploymentManifest | None,
    candidate: DeploymentManifest,
    *,
    allow_same_version: bool = False,
) -> bool:
    """Return whether *candidate* is newer than the active release."""
    if active is None:
        return True
    if active.commit == candidate.commit and Version(active.version) == Version(candidate.version):
        return False
    candidate_version = Version(candidate.version)
    active_version = Version(active.version)
    if candidate_version < active_version or (
        candidate_version == active_version and not allow_same_version
    ):
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
                    payload = RuntimeHealth.model_validate_json(response.read())
                if payload.version != manifest.version:
                    raise ValueError(f"version is {payload.version}")
                if payload.commit != manifest.commit:
                    raise ValueError(f"commit is {payload.commit}")
                if payload.instance != endpoint.instance:
                    raise ValueError(f"instance is {payload.instance}")
                if (
                    endpoint.control_mode
                    and payload.control_mode != endpoint.control_mode
                ):
                    raise ValueError(f"control mode is {payload.control_mode}")
            except (OSError, ValueError, json.JSONDecodeError) as error:
                errors.append(f"{endpoint.url}: {error}")
        if not errors:
            return
        time.sleep(1)
    raise RuntimeError("release health checks failed: " + "; ".join(errors))


def _unit_fragment(unit: str, systemctl: str) -> Path:
    result = subprocess.run(
        [systemctl, "show", unit, "--property=FragmentPath", "--value"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    fragment = Path(result.stdout.strip())
    if not fragment.is_absolute() or not fragment.is_file():
        raise ValueError(f"cannot locate installed systemd unit {unit}")
    return fragment


def _check_activation_preflight(
    target: DeploymentTarget,
    candidate_release: Path,
    candidate: DeploymentManifest,
    systemctl: str,
) -> None:
    """Refuse to stop services when target policy or unit bytes have drifted."""
    candidate_units = {
        Path(path).name: candidate_release / path for path in candidate.systemd_units
    }
    drifted: list[str] = []
    for unit in dict.fromkeys((*target.quiesce_units, *target.resume_units)):
        packaged = candidate_units.get(unit)
        if packaged is None:
            drifted.append(f"{unit} (missing from candidate)")
            continue
        fragment = _unit_fragment(unit, systemctl)
        if fragment.read_bytes() != packaged.read_bytes():
            drifted.append(f"{unit} ({fragment})")
    if drifted:
        raise ValueError(
            "installed systemd unit definitions differ from the candidate; "
            "install the reviewed host configuration before activation: "
            + ", ".join(drifted)
        )
    for endpoint in target.health:
        if endpoint.control_mode is None:
            continue
        try:
            with urllib.request.urlopen(endpoint.url, timeout=3) as response:
                payload = RuntimeHealth.model_validate_json(response.read())
        except (OSError, ValueError) as error:
            raise ValueError(f"cannot verify active target {endpoint.url}: {error}") from error
        if payload.instance != endpoint.instance:
            raise ValueError(
                f"active target {endpoint.url} reports instance {payload.instance}; "
                f"expected {endpoint.instance}"
            )
        if payload.control_mode != endpoint.control_mode:
            raise ValueError(
                f"active target {endpoint.instance} uses control mode "
                f"{payload.control_mode}; expected {endpoint.control_mode}; "
                "reconcile the reviewed host environment before activation"
            )


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
    staged = install_package(
        package,
        target.root,
        uv=options.uv,
        python=options.python,
        create_venv=options.create_venv,
        activate=False,
    )
    _check_activation_preflight(
        target,
        staged.release_directory,
        candidate,
        options.systemctl,
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
            uv=options.uv,
            python=options.python,
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
    if (options.branch or options.commit) and target.name != "staging":
        raise ValueError("branch and commit sources are restricted to staging")
    active = active_manifest(target)
    with tempfile.TemporaryDirectory(prefix="temperature-bot-release-") as temporary:
        temporary_path = Path(temporary)
        source_selection = None
        release: GitHubRelease | None = None
        if options.branch or options.commit:
            kind: Literal["branch", "commit"] = (
                "branch" if options.branch else "commit"
            )
            value = options.branch or options.commit
            assert value is not None
            source_selection = resolve_source_selection(
                options.repository,
                kind,
                value,
                api_base=options.api_base,
            )
            expected_commit = source_selection.commit
            source_url = source_selection.html_url
            source_label = f"{kind}:{value}"
        else:
            release = discover_release(
                options.repository,
                options.channel,
                api_base=options.api_base,
                tag=options.tag,
            )
            expected_commit = resolve_tag_commit(
                options.repository, release.tag_name, api_base=options.api_base
            )
            source_url = release.html_url
            source_label = release.tag_name
        if active and active.commit == expected_commit:
            return UpdateResult(
                checked_at=datetime.now(timezone.utc),
                target=target.name,
                release_url=source_url,
                tag=source_label,
                version=active.version,
                commit=active.commit,
                disposition="current",
                release_directory=(target.root / "current").resolve(),
            )
        if source_selection:
            package, manifest = build_source_package(
                source_selection,
                temporary_path,
                SourceBuildOptions(
                    repository=options.repository,
                    uv=options.uv,
                    python=options.python,
                    build_user=options.build_user,
                ),
            )
        else:
            assert release is not None
            package, manifest = download_and_verify(
                release, expected_commit, temporary_path
            )
        update_required(
            active,
            manifest,
            allow_same_version=source_selection is not None,
        )
        disposition: Literal["available", "staged", "activated"] = "available"
        release_directory = None
        if not options.check_only:
            target.root.mkdir(parents=True, exist_ok=True)
            with (target.root / ".release-update.lock").open("a+b") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                installation = install_package(
                    package,
                    target.root,
                    uv=options.uv,
                    python=options.python,
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
                            release_url=source_url,
                            tag=source_label,
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
                        package,
                        target,
                        active,
                        manifest,
                        ActivationOptions(
                            create_venv=options.create_venv,
                            uv=options.uv,
                            python=options.python,
                        ),
                    )
                    disposition = "activated"
        result = UpdateResult(
            checked_at=datetime.now(timezone.utc),
            target=target.name,
            release_url=source_url,
            tag=source_label,
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
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--tag", help="select one exact published release tag")
    source.add_argument("--branch", help="build one GitHub branch head")
    source.add_argument("--commit", help="build one exact GitHub commit SHA")
    parser.add_argument("--uv", default=DEFAULT_UV)
    parser.add_argument("--python", default="3.12")
    parser.add_argument("--build-user", default=DEFAULT_BUILD_USER)
    args = parser.parse_args(argv)
    if args.activate and args.check_only:
        parser.error("--activate cannot be combined with --check-only")
    try:
        result = run_update(
            TARGETS[args.target],
            UpdateOptions(
                repository=args.repository,
                channel=args.channel,
                tag=args.tag,
                branch=args.branch,
                commit=args.commit,
                check_only=args.check_only,
                activate=args.activate,
                uv=args.uv,
                python=args.python,
                build_user=args.build_user,
            ),
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
