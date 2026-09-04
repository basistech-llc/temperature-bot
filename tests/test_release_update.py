"""Release-tag and GitHub release updater integration tests."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from app.deployment_package import (
    PackageIdentity,
    PayloadSource,
    build_package,
    verify_package,
)
from bin.github_release_update import (
    ActivationOptions,
    DeploymentTarget,
    HealthEndpoint,
    ReleaseChannel,
    UpdateResult,
    UpdateOptions,
    activate_schema_neutral_release,
    activation_is_schema_neutral,
    discover_release,
    run_update,
    update_required,
)
from bin.install_deployment_package import install_package
from bin.release_tag import validate_tag


class ReleaseServer(BaseHTTPRequestHandler):
    """Serve deterministic GitHub API and release-asset responses."""

    routes: dict[str, tuple[str, bytes]] = {}

    def do_GET(self):  # noqa: N802
        try:
            content_type, body = self.routes[self.path]
        except KeyError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # pylint: disable=redefined-builtin
        del format, args


def _source(root: Path, name: str, data: bytes) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _package(
    root: Path, version: str, commit: str, migration: bytes = b"SELECT 1;\n"
) -> Path:
    package = root / f"temperature-bot-deployment-{version}-{commit[:12]}.zip"
    build_package(
        package,
        PackageIdentity(
            version=version,
            commit=commit,
            built_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
            requires_python=">=3.12",
            flyway_version="12.8.1",
        ),
        [
            PayloadSource(
                source=_source(root, "temperature_bot.whl", b"wheel"),
                path=f"wheel/temperature_bot-{version}-py3-none-any.whl",
                role="wheel",
            ),
            PayloadSource(
                source=_source(root, "runtime.txt", b""),
                path="requirements/runtime.txt",
                role="requirements",
            ),
            PayloadSource(
                source=_source(root, "V1.sql", migration),
                path="migrations/V1.sql",
                role="migration",
            ),
        ],
    )
    return package


def _systemctl(tmp_path: Path, active: bool = True) -> tuple[Path, Path]:
    state = tmp_path / "systemd-state.json"
    state.write_text(
        json.dumps({"web.service": active, "events": []}), encoding="utf-8"
    )
    command = tmp_path / "systemctl"
    command.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

state_path = Path(sys.argv[0]).with_name("systemd-state.json")
state = json.loads(state_path.read_text())
action = sys.argv[1]
unit = sys.argv[-1]
if action == "is-active":
    raise SystemExit(0 if state.get(unit, False) else 3)
if action not in {"start", "stop"}:
    raise SystemExit(2)
state[unit] = action == "start"
state["events"].append([action, unit])
state_path.write_text(json.dumps(state))
""",
        encoding="utf-8",
    )
    command.chmod(0o755)
    return command, state


def _activation_target(root: Path, port: int) -> DeploymentTarget:
    return DeploymentTarget(
        name="test",
        root=root,
        quiesce_units=("web.service",),
        resume_units=("web.service",),
        health=(
            HealthEndpoint(
                url=f"http://127.0.0.1:{port}/api/v1/version", instance="test"
            ),
        ),
    )


@pytest.fixture
def release_api(tmp_path):
    commit = "a" * 40
    package = _package(tmp_path, "1.0a1", commit)
    checksum = package.with_suffix(".zip.sha256")
    server = ThreadingHTTPServer(("127.0.0.1", 0), ReleaseServer)
    base = f"http://127.0.0.1:{server.server_port}"
    release = {
        "tag_name": "1.0-alpha1",
        "html_url": f"{base}/release",
        "draft": False,
        "prerelease": True,
        "assets": [
            {
                "name": package.name,
                "browser_download_url": f"{base}/assets/{package.name}",
                "size": package.stat().st_size,
            },
            {
                "name": checksum.name,
                "browser_download_url": f"{base}/assets/{checksum.name}",
                "size": checksum.stat().st_size,
            },
        ],
    }
    screenshot_release = {
        "tag_name": "web-ui-screenshots-pr-999",
        "html_url": f"{base}/screenshot-release",
        "draft": False,
        "prerelease": True,
        "assets": [],
    }
    ReleaseServer.routes = {
        "/repos/basistech-llc/temperature-bot/releases?per_page=100&page=1": (
            "application/json",
            json.dumps([screenshot_release, release]).encode(),
        ),
        "/repos/basistech-llc/temperature-bot/releases/tags/1.0-alpha1": (
            "application/json",
            json.dumps(release).encode(),
        ),
        "/repos/basistech-llc/temperature-bot/git/ref/tags/1.0-alpha1": (
            "application/json",
            json.dumps({"object": {"sha": commit, "type": "commit"}}).encode(),
        ),
        f"/assets/{package.name}": ("application/zip", package.read_bytes()),
        f"/assets/{checksum.name}": ("text/plain", checksum.read_bytes()),
    }
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield base, commit
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_alpha_tag_alias_is_legal_for_canonical_version():
    assert str(validate_tag("1.0.0-alpha2")) == "1.0.0a2"


def test_release_update_downloads_verifies_and_stages(release_api, tmp_path):
    api_base, commit = release_api
    target = DeploymentTarget(
        name="test",
        root=tmp_path / "install",
        quiesce_units=(),
        resume_units=(),
        health=(HealthEndpoint(url="http://127.0.0.1", instance="test"),),
    )

    result = run_update(
        target,
        UpdateOptions(
            channel=ReleaseChannel.PRERELEASE,
            api_base=api_base,
            create_venv=False,
        ),
    )

    assert result.disposition == "staged"
    assert result.version == "1.0a1"
    assert result.commit == commit
    assert result.release_directory == target.root / f"releases/1.0a1-{commit[:12]}"
    state = UpdateResult.model_validate_json(
        (target.root / "release-update-state.json").read_bytes()
    )
    assert state == result


def test_release_discovery_skips_unrelated_screenshot_releases(release_api):
    api_base, _commit = release_api

    release = discover_release(
        "basistech-llc/temperature-bot",
        ReleaseChannel.PRERELEASE,
        api_base=api_base,
    )

    assert release.tag_name == "1.0-alpha1"


def test_release_update_can_select_an_exact_tag(release_api, tmp_path):
    api_base, commit = release_api
    target = DeploymentTarget(
        name="test",
        root=tmp_path / "install",
        quiesce_units=(),
        resume_units=(),
        health=(HealthEndpoint(url="http://127.0.0.1", instance="test"),),
    )

    result = run_update(
        target,
        UpdateOptions(
            channel=ReleaseChannel.PRERELEASE,
            api_base=api_base,
            tag="1.0-alpha1",
            check_only=True,
            create_venv=False,
        ),
    )

    assert result.disposition == "available"
    assert result.tag == "1.0-alpha1"
    assert result.commit == commit


def test_activation_refuses_changed_migrations(tmp_path):
    active = verify_package(_package(tmp_path / "active", "0.9", "a" * 40))
    candidate = verify_package(
        _package(tmp_path / "candidate", "1.0", "b" * 40, b"SELECT 2;\n")
    )

    assert not activation_is_schema_neutral(active, candidate)
    assert update_required(active, candidate)


def test_update_refuses_older_release(tmp_path):
    active = verify_package(_package(tmp_path / "active", "2.0", "a" * 40))
    candidate = verify_package(_package(tmp_path / "candidate", "1.0", "b" * 40))

    with pytest.raises(ValueError, match="refusing non-newer release"):
        update_required(active, candidate)


def test_schema_neutral_activation_restores_units(tmp_path):
    active_package = _package(tmp_path / "active", "0.9", "a" * 40)
    candidate_package = _package(tmp_path / "candidate", "1.0", "b" * 40)
    active = verify_package(active_package)
    candidate = verify_package(candidate_package)
    root = tmp_path / "root"
    install_package(active_package, root, create_venv=False, activate=True)
    command, state = _systemctl(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), ReleaseServer)
    ReleaseServer.routes = {
        "/api/v1/version": (
            "application/json",
            json.dumps(
                {"version": "1.0", "commit": "b" * 40, "instance": "test"}
            ).encode(),
        )
    }
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        release = activate_schema_neutral_release(
            candidate_package,
            _activation_target(root, server.server_port),
            active,
            candidate,
            ActivationOptions(
                require_root=False,
                systemctl=str(command),
                create_venv=False,
                health_timeout=2,
            ),
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    assert (root / "current").resolve() == release
    assert json.loads(state.read_text())["web.service"] is True


def test_failed_health_rolls_back_release_and_units(tmp_path):
    active_package = _package(tmp_path / "active", "0.9", "a" * 40)
    candidate_package = _package(tmp_path / "candidate", "1.0", "b" * 40)
    active = verify_package(active_package)
    candidate = verify_package(candidate_package)
    root = tmp_path / "root"
    installed = install_package(
        active_package, root, create_venv=False, activate=True
    )
    command, state = _systemctl(tmp_path)
    target = _activation_target(root, 1)

    with pytest.raises(RuntimeError, match="health checks failed"):
        activate_schema_neutral_release(
            candidate_package,
            target,
            active,
            candidate,
            ActivationOptions(
                require_root=False,
                systemctl=str(command),
                create_venv=False,
                health_timeout=0.1,
            ),
        )

    assert (root / "current").resolve() == installed.release_directory
    systemd_state = json.loads(state.read_text())
    assert systemd_state["web.service"] is True
    assert systemd_state["events"] == [
        ["stop", "web.service"],
        ["start", "web.service"],
        ["stop", "web.service"],
        ["start", "web.service"],
    ]


def test_activation_refuses_control_mode_drift_before_stopping_units(tmp_path):
    active_package = _package(tmp_path / "active", "0.9", "a" * 40)
    candidate_package = _package(tmp_path / "candidate", "1.0", "b" * 40)
    active = verify_package(active_package)
    candidate = verify_package(candidate_package)
    root = tmp_path / "root"
    installed = install_package(
        active_package, root, create_venv=False, activate=True
    )
    command, state = _systemctl(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), ReleaseServer)
    ReleaseServer.routes = {
        "/api/v1/version": (
            "application/json",
            json.dumps(
                {
                    "version": "0.9",
                    "commit": "a" * 40,
                    "instance": "test",
                    "control_mode": "read-only",
                }
            ).encode(),
        )
    }
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    target = DeploymentTarget(
        name="test",
        root=root,
        quiesce_units=("web.service",),
        resume_units=("web.service",),
        health=(
            HealthEndpoint(
                url=f"http://127.0.0.1:{server.server_port}/api/v1/version",
                instance="test",
                control_mode="live",
            ),
        ),
    )
    try:
        with pytest.raises(ValueError, match="uses control mode read-only"):
            activate_schema_neutral_release(
                candidate_package,
                target,
                active,
                candidate,
                ActivationOptions(
                    require_root=False,
                    systemctl=str(command),
                    create_venv=False,
                    health_timeout=1,
                ),
            )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    assert (root / "current").resolve() == installed.release_directory
    assert json.loads(state.read_text())["events"] == []
