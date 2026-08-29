"""Substantive deployment ZIP integrity and installation tests."""

from __future__ import annotations

import json
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.deployment_package import (
    MANIFEST_PATH,
    DeploymentManifest,
    PackageIdentity,
    PayloadSource,
    build_package,
    extract_verified_package,
    verify_outer_checksum,
    verify_package,
)
from bin.build_deployment_package import collect_payloads
from bin.install_deployment_package import install_package, main as installer_main


def _source(root: Path, relative: str, data: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _package(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    payloads = [
        PayloadSource(
            source=_source(source, "app.whl", b"wheel"),
            path="wheel/temperature_bot-1.2.3-py3-none-any.whl",
            role="wheel",
        ),
        PayloadSource(
            source=_source(source, "runtime.txt", b"pydantic==2.0\n"),
            path="requirements/runtime.txt",
            role="requirements",
        ),
        PayloadSource(
            source=_source(source, "V1.sql", b"SELECT 1;\n"),
            path="migrations/V1.sql",
            role="migration",
        ),
        PayloadSource(
            source=_source(source, "minute.service", b"[Service]\nType=oneshot\n"),
            path="systemd/minute.service",
            role="systemd",
        ),
        PayloadSource(
            source=_source(source, "runtime.env.example", b"LOG_LEVEL=INFO\n"),
            path="configuration/runtime.env.example",
            role="configuration",
        ),
        PayloadSource(
            source=_source(source, "install.py", b"#!/usr/bin/env python3\n"),
            path="installer/install.py",
            role="installer",
            mode=0o755,
        ),
    ]
    package = tmp_path / "temperature-bot.zip"
    build_package(
        package,
        PackageIdentity(
            version="1.2.3",
            commit="a" * 40,
            built_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
            requires_python=">=3.12",
            flyway_version="12.8.1",
        ),
        payloads,
    )
    return package


def test_build_verify_and_safe_extract_round_trip(tmp_path):
    package = _package(tmp_path)
    verify_outer_checksum(package)
    manifest = verify_package(package)

    assert manifest.version == "1.2.3"
    assert manifest.migrations == ["migrations/V1.sql"]
    assert manifest.systemd_units == ["systemd/minute.service"]

    destination = tmp_path / "extracted"
    extract_verified_package(package, destination)
    assert (destination / "migrations/V1.sql").read_text() == "SELECT 1;\n"
    assert stat.S_IMODE((destination / "installer/install.py").stat().st_mode) == 0o755


def test_builder_collects_complete_migrations_units_and_configuration(tmp_path):
    wheel = _source(tmp_path, "temperature_bot-1.2.3-py3-none-any.whl", b"wheel")
    requirements = _source(tmp_path, "runtime.txt", b"pydantic==2.0\n")
    payloads = collect_payloads(requirements, wheel)
    paths = {payload.path for payload in payloads}

    repo_root = Path(__file__).resolve().parents[1]
    expected_migrations = {
        f"migrations/{path.name}" for path in (repo_root / "etc/flyway/sql").glob("*.sql")
    }
    expected_units = {
        f"systemd/{path.name}"
        for path in (repo_root / "etc/systemd").iterdir()
        if path.is_file() and path.suffix in {".service", ".timer"}
    }

    assert "configuration/temperature-bot.env.example" in paths
    assert "configuration/slg1.env.example" in paths
    assert "configuration/deg1.env.example" in paths
    assert "systemd/slg1_basistech_net.service" in paths
    assert "systemd/deg1_basistech_net.service" in paths
    assert "configuration/slg1_basistech_net.socket" in paths
    assert "configuration/deg1_basistech_net.socket" in paths
    assert "documentation/DEPLOYMENT_PACKAGE.md" in paths
    assert "installer/install_deployment_package.py" in paths
    assert {payload.path for payload in payloads if payload.role == "migration"} == (
        expected_migrations
    )
    assert {payload.path for payload in payloads if payload.role == "systemd"} == expected_units


def test_developer_units_use_socket_activation_and_private_network():
    repo_root = Path(__file__).resolve().parents[1]
    for instance, port in (("slg1", 8003), ("deg1", 8004)):
        service = (repo_root / f"etc/systemd/{instance}_basistech_net.service").read_text()
        socket_unit = (
            repo_root / f"etc/systemd/{instance}_basistech_net.socket"
        ).read_text()

        assert "PrivateNetwork=yes" in service
        assert "--bind fd://3" in service
        assert f"Requires={instance}_basistech_net.socket" in service
        assert f"ListenStream=127.0.0.1:{port}" in socket_unit


def test_builder_rejects_reserved_manifest_payload(tmp_path):
    package = tmp_path / "temperature-bot.zip"
    payloads = [
        PayloadSource(
            source=_source(tmp_path, "manifest-source.json", b"{}"),
            path=MANIFEST_PATH,
            role="metadata",
        )
    ]

    with pytest.raises(ValueError, match="payload path is reserved: manifest.json"):
        build_package(
            package,
            PackageIdentity(
                version="1.2.3",
                commit="a" * 40,
                built_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
                requires_python=">=3.12",
                flyway_version="12.8.1",
            ),
            payloads,
        )


def test_installer_verify_only_cli_emits_valid_manifest(tmp_path, capsys):
    package = _package(tmp_path)

    installer_main([str(package), "--require-checksum", "--verify-only"])

    manifest = DeploymentManifest.model_validate(json.loads(capsys.readouterr().out))
    assert manifest.version == "1.2.3"
    assert manifest.systemd_units == ["systemd/minute.service"]


def test_installer_stages_atomically_and_activates_relative_symlink(tmp_path):
    package = _package(tmp_path)
    root = tmp_path / "opt/temperature-bot"
    systemd_dir = tmp_path / "etc/systemd/system"

    result = install_package(
        package,
        root,
        create_venv=False,
        activate=True,
        systemd_dir=systemd_dir,
    )

    assert result.release_directory == root / "releases/1.2.3-aaaaaaaaaaaa"
    assert (root / "current").readlink() == Path("releases/1.2.3-aaaaaaaaaaaa")
    assert (systemd_dir / "minute.service").read_text() == "[Service]\nType=oneshot\n"
    assert not (systemd_dir / "runtime.env.example").exists()
    assert not list((root / "releases").glob("*.staging.*"))


def test_installer_revalidates_existing_immutable_payload(tmp_path):
    package = _package(tmp_path)
    root = tmp_path / "opt/temperature-bot"
    result = install_package(package, root, create_venv=False)
    (result.release_directory / "migrations/V1.sql").write_text("SELECT 2;\n")

    with pytest.raises(ValueError, match="installed release SHA-256 mismatch"):
        install_package(package, root, create_venv=False)


def test_verifier_rejects_payload_changed_after_manifest(tmp_path):
    package = _package(tmp_path)
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(package) as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename.endswith("V1.sql"):
                data = b"SELECT 2;\n"
            target.writestr(info, data)

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_package(tampered)


def test_verifier_rejects_unlisted_member(tmp_path):
    package = _package(tmp_path)
    with zipfile.ZipFile(package, "a") as archive:
        archive.writestr("unexpected.txt", "not in manifest")

    with pytest.raises(ValueError, match="outer SHA-256 mismatch"):
        verify_outer_checksum(package)
    with pytest.raises(ValueError, match="inventory mismatch"):
        verify_package(package)


@pytest.mark.parametrize("path", ["/absolute", "../escape", "a/../escape", r"a\b"])
def test_payload_rejects_unsafe_member_paths(tmp_path, path):
    source = _source(tmp_path, "payload", b"data")
    with pytest.raises(ValidationError, match="unsafe deployment package path"):
        PayloadSource(source=source, path=path, role="metadata")


def test_manifest_is_first_for_fast_inspection(tmp_path):
    package = _package(tmp_path)
    with zipfile.ZipFile(package) as archive:
        assert archive.namelist()[0] == MANIFEST_PATH
