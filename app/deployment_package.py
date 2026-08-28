"""Build, verify, and safely extract Temperature Bot deployment packages."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MANIFEST_PATH = "manifest.json"
PACKAGE_FORMAT_VERSION: Literal[1] = 1
PackageRole = Literal[
    "wheel",
    "requirements",
    "migration",
    "systemd",
    "configuration",
    "installer",
    "documentation",
    "metadata",
]


def validate_package_path(value: str) -> str:
    """Return a normalized safe relative ZIP member path."""
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or str(path) != value
    ):
        raise ValueError(f"unsafe deployment package path: {value!r}")
    return value


class PayloadSource(BaseModel):
    """One source file and its intended path inside a deployment ZIP."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    source: Path
    path: str
    role: PackageRole
    mode: int = Field(default=0o644, ge=0, le=0o777)

    _safe_path = field_validator("path")(validate_package_path)

    @field_validator("source")
    @classmethod
    def source_is_file(cls, value: Path) -> Path:
        if not value.is_file():
            raise ValueError(f"deployment payload is not a file: {value}")
        return value


class PackageFile(BaseModel):
    """Integrity and installation metadata for one ZIP member."""

    model_config = ConfigDict(extra="forbid")

    path: str
    role: PackageRole
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)
    mode: int = Field(ge=0, le=0o777)

    _safe_path = field_validator("path")(validate_package_path)


class PackageIdentity(BaseModel):
    """Build identity recorded independently of mutable Git state."""

    model_config = ConfigDict(extra="forbid")

    application: Literal["temperature-bot"] = "temperature-bot"
    version: str = Field(min_length=1)
    commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    built_at: datetime
    dirty: bool = False
    requires_python: str = Field(min_length=1)
    flyway_version: str = Field(min_length=1)


class DeploymentManifest(PackageIdentity):
    """Canonical contract for one deployment package."""

    format_version: Literal[1] = PACKAGE_FORMAT_VERSION
    wheel: str
    requirements: str
    migrations: list[str]
    systemd_units: list[str]
    files: list[PackageFile]

    _safe_wheel = field_validator("wheel")(validate_package_path)
    _safe_requirements = field_validator("requirements")(validate_package_path)

    @field_validator("migrations", "systemd_units")
    @classmethod
    def safe_path_list(cls, values: list[str]) -> list[str]:
        return [validate_package_path(value) for value in values]

    @model_validator(mode="after")
    def validate_inventory(self) -> "DeploymentManifest":
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("deployment manifest contains duplicate paths")
        wheel_paths = [item.path for item in self.files if item.role == "wheel"]
        if wheel_paths != [self.wheel]:
            raise ValueError("wheel does not identify a wheel payload")
        requirement_paths = [item.path for item in self.files if item.role == "requirements"]
        if requirement_paths != [self.requirements]:
            raise ValueError("requirements does not identify a requirements payload")
        migration_paths = sorted(item.path for item in self.files if item.role == "migration")
        if self.migrations != migration_paths:
            raise ValueError("migration list does not match payload inventory")
        unit_paths = sorted(item.path for item in self.files if item.role == "systemd")
        if self.systemd_units != unit_paths:
            raise ValueError("systemd unit list does not match payload inventory")
        unit_names = [PurePosixPath(path).name for path in self.systemd_units]
        if len(unit_names) != len(set(unit_names)):
            raise ValueError("systemd unit names are not unique")
        if any(PurePosixPath(path).suffix not in {".service", ".timer"} for path in unit_paths):
            raise ValueError("systemd payload is not a service or timer")
        return self


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _zip_info(path: str, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path)
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | mode) << 16
    return info


def _single_role(payloads: list[PayloadSource], role: PackageRole) -> str:
    paths = [payload.path for payload in payloads if payload.role == role]
    if len(paths) != 1:
        raise ValueError(f"deployment package requires exactly one {role} payload")
    return paths[0]


def build_package(
    output: Path, identity: PackageIdentity, payloads: list[PayloadSource]
) -> DeploymentManifest:
    """Create an atomic ZIP and outer SHA-256 sidecar."""
    paths = [payload.path for payload in payloads]
    if len(paths) != len(set(paths)):
        raise ValueError("deployment payload contains duplicate paths")

    files = [
        PackageFile(
            path=payload.path,
            role=payload.role,
            sha256=sha256_file(payload.source),
            size=payload.source.stat().st_size,
            mode=payload.mode,
        )
        for payload in sorted(payloads, key=lambda item: item.path)
    ]
    manifest = DeploymentManifest(
        **identity.model_dump(),
        wheel=_single_role(payloads, "wheel"),
        requirements=_single_role(payloads, "requirements"),
        migrations=sorted(payload.path for payload in payloads if payload.role == "migration"),
        systemd_units=sorted(payload.path for payload in payloads if payload.role == "systemd"),
        files=files,
    )
    manifest_bytes = (manifest.model_dump_json(indent=2) + "\n").encode()

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".zip", delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        with zipfile.ZipFile(
            temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            archive.writestr(_zip_info(MANIFEST_PATH, 0o644), manifest_bytes)
            for payload in sorted(payloads, key=lambda item: item.path):
                archive.writestr(
                    _zip_info(payload.path, payload.mode), payload.source.read_bytes()
                )
        os.replace(temp_path, output)
    finally:
        temp_path.unlink(missing_ok=True)

    checksum_path = output.with_suffix(output.suffix + ".sha256")
    checksum_path.write_text(f"{sha256_file(output)}  {output.name}\n", encoding="utf-8")
    return manifest


def _read_manifest(archive: zipfile.ZipFile) -> DeploymentManifest:
    try:
        raw_manifest = archive.read(MANIFEST_PATH)
    except KeyError as error:
        raise ValueError("deployment package has no manifest.json") from error
    try:
        return DeploymentManifest.model_validate_json(raw_manifest)
    except ValueError as error:
        raise ValueError(f"invalid deployment manifest: {error}") from error


def verify_package(package: Path) -> DeploymentManifest:
    """Validate ZIP structure, CRCs, manifest, modes, sizes, and SHA-256 hashes."""
    with zipfile.ZipFile(package) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("deployment package contains duplicate ZIP members")
        for info in infos:
            validate_package_path(info.filename)
            file_type = (info.external_attr >> 16) & 0o170000
            if file_type not in {0, stat.S_IFREG}:
                raise ValueError(f"deployment package member is not a regular file: {info.filename}")
        corrupt = archive.testzip()
        if corrupt is not None:
            raise ValueError(f"deployment package CRC check failed: {corrupt}")

        manifest = _read_manifest(archive)
        expected = {MANIFEST_PATH, *(item.path for item in manifest.files)}
        if set(names) != expected:
            missing = sorted(expected - set(names))
            extra = sorted(set(names) - expected)
            raise ValueError(f"deployment package inventory mismatch; missing={missing}, extra={extra}")

        by_name = {info.filename: info for info in infos}
        for item in manifest.files:
            data = archive.read(item.path)
            if len(data) != item.size:
                raise ValueError(f"deployment package size mismatch: {item.path}")
            if sha256_bytes(data) != item.sha256:
                raise ValueError(f"deployment package SHA-256 mismatch: {item.path}")
            mode = (by_name[item.path].external_attr >> 16) & 0o777
            if mode != item.mode:
                raise ValueError(f"deployment package mode mismatch: {item.path}")
        return manifest


def verify_outer_checksum(package: Path, checksum_path: Path | None = None) -> None:
    """Verify the builder's whole-ZIP SHA-256 sidecar."""
    sidecar = checksum_path or package.with_suffix(package.suffix + ".sha256")
    fields = sidecar.read_text(encoding="utf-8").strip().split()
    if len(fields) != 2 or fields[1] != package.name:
        raise ValueError(f"invalid deployment package checksum file: {sidecar}")
    if fields[0] != sha256_file(package):
        raise ValueError("deployment package outer SHA-256 mismatch")


def extract_verified_package(package: Path, destination: Path) -> DeploymentManifest:
    """Verify and extract without extractall(), symlinks, or path traversal."""
    manifest = verify_package(package)
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir(parents=True)
    with zipfile.ZipFile(package) as archive:
        for item in manifest.files:
            target = destination.joinpath(*PurePosixPath(item.path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(item.path))
            target.chmod(item.mode)
        manifest_target = destination / MANIFEST_PATH
        manifest_target.write_bytes(archive.read(MANIFEST_PATH))
        manifest_target.chmod(0o644)
    return manifest


def verify_extracted_payload(destination: Path, manifest: DeploymentManifest) -> None:
    """Verify immutable package files in an existing release directory."""
    for item in manifest.files:
        target = destination.joinpath(*PurePosixPath(item.path).parts)
        if not target.is_file() or target.is_symlink():
            raise ValueError(f"installed release payload is not a regular file: {item.path}")
        file_stat = target.stat()
        if file_stat.st_size != item.size:
            raise ValueError(f"installed release size mismatch: {item.path}")
        if sha256_file(target) != item.sha256:
            raise ValueError(f"installed release SHA-256 mismatch: {item.path}")
        if stat.S_IMODE(file_stat.st_mode) != item.mode:
            raise ValueError(f"installed release mode mismatch: {item.path}")
