"""Release-tag and GitHub release updater integration tests."""

from __future__ import annotations

import json
import os
import pwd
import shutil
import subprocess
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
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
from app.instance_policy import IntegrationModes
from bin.github_release_update import (
    ActivationOptions,
    DeploymentTarget,
    HealthEndpoint,
    ReleaseChannel,
    RuntimeHealth,
    UpdateCandidate,
    UpdateResult,
    UpdateOptions,
    _check_runtime_policy,
    _stage_candidate,
    active_manifest,
    activate_schema_neutral_release,
    activation_is_schema_neutral,
    discover_release,
    resolve_source_selection,
    run_update,
    update_required,
)
from bin.install_deployment_package import _verify_environment, install_package
from bin.release_tag import validate_tag
from bin.source_deployment import (
    SourceBuildOptions,
    SourceSelection,
    _copy_builder_output,
    build_source_package,
)


class ReleaseServer(BaseHTTPRequestHandler):
    """Serve deterministic GitHub API and release-asset responses."""

    routes: dict[str, tuple[str, bytes]] = {}
    block_path: str | None = None
    request_started: threading.Event | None = None
    continue_response: threading.Event | None = None

    def do_GET(self):  # noqa: N802
        if self.path == self.block_path:
            assert self.request_started is not None
            assert self.continue_response is not None
            self.request_started.set()
            if not self.continue_response.wait(timeout=10):
                self.send_error(504)
                return
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


def _wheel_with_import_side_effect(
    root: Path, version: str, sentinel: Path
) -> Path:
    wheel = root / f"temperature_bot-{version}-py3-none-any.whl"
    dist_info = f"temperature_bot-{version}.dist-info"
    files = {
        "app/__init__.py": b"",
        "app/version.py": (
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('executed')\n"
            f"__version__ = {version!r}\n"
        ).encode(),
        "app/clogging.py": b"",
        "app/deployment_package.py": b"",
        "bin/__init__.py": b"",
        "bin/runner.py": b"",
        "bin/github_release_update.py": b"",
        "bin/source_deployment.py": b"",
        f"{dist_info}/METADATA": (
            "Metadata-Version: 2.1\n"
            "Name: temperature-bot\n"
            f"Version: {version}\n"
        ).encode(),
        f"{dist_info}/WHEEL": (
            "Wheel-Version: 1.0\n"
            "Generator: temperature-bot-test\n"
            "Root-Is-Purelib: true\n"
            "Tag: py3-none-any\n"
        ).encode(),
        f"{dist_info}/entry_points.txt": (
            "[console_scripts]\n"
            "gunicorn = app.version:main\n"
        ).encode(),
    }
    record = "".join(f"{name},,\n" for name in (*files, f"{dist_info}/RECORD"))
    files[f"{dist_info}/RECORD"] = record.encode()
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return wheel


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
            PayloadSource(
                source=_source(root, "web.service", b"[Service]\nExecStart=true\n"),
                path="systemd/web.service",
                role="systemd",
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
    installed_units = tmp_path / "installed-units"
    installed_units.mkdir()
    (installed_units / "web.service").write_text(
        "[Service]\nExecStart=true\n", encoding="utf-8"
    )
    command.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

state_path = Path(sys.argv[0]).with_name("systemd-state.json")
state = json.loads(state_path.read_text())
action = sys.argv[1]
unit = sys.argv[-1]
if action == "show":
    print(f"FragmentPath={Path(sys.argv[0]).with_name('installed-units') / sys.argv[2]}")
    print(f"DropInPaths={state.get('drop_in_paths', '')}")
    raise SystemExit(0)
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
        "/repos/basistech-llc/temperature-bot/commits/codex%2Frelease-readiness-a2": (
            "application/json",
            json.dumps(
                {"sha": commit, "html_url": f"{base}/commit/{commit}"}
            ).encode(),
        ),
        f"/repos/basistech-llc/temperature-bot/commits/{commit[:12]}": (
            "application/json",
            json.dumps(
                {"sha": commit, "html_url": f"{base}/commit/{commit}"}
            ).encode(),
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


def test_beta_tag_alias_is_legal_for_canonical_version():
    assert str(validate_tag("1.0.0-beta1")) == "1.0.0b1"


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


def test_concurrent_newer_release_rejects_stale_candidate(release_api, tmp_path):
    api_base, _commit = release_api
    target = DeploymentTarget(
        name="test",
        root=tmp_path / "install",
        quiesce_units=(),
        resume_units=(),
        health=(),
    )
    initial = _package(tmp_path / "initial", "0.9", "0" * 40)
    install_package(initial, target.root, create_venv=False, activate=True)
    package_path = next(
        path
        for path, (content_type, _body) in ReleaseServer.routes.items()
        if content_type == "application/zip"
    )
    ReleaseServer.block_path = package_path
    ReleaseServer.request_started = threading.Event()
    ReleaseServer.continue_response = threading.Event()
    options = UpdateOptions(
        channel=ReleaseChannel.PRERELEASE,
        api_base=api_base,
        create_venv=False,
    )

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_update, target, options)
            assert ReleaseServer.request_started.wait(timeout=5)
            newer = _package(tmp_path / "newer", "2.0", "b" * 40)
            install_package(newer, target.root, create_venv=False, activate=True)
            ReleaseServer.continue_response.set()
            with pytest.raises(ValueError, match="refusing non-newer release"):
                future.result(timeout=10)
    finally:
        assert ReleaseServer.continue_response is not None
        ReleaseServer.continue_response.set()
        ReleaseServer.block_path = None
        ReleaseServer.request_started = None
        ReleaseServer.continue_response = None

    current = active_manifest(target)
    assert current is not None
    assert current.version == "2.0"
    assert not (target.root / "releases/1.0a1-aaaaaaaaaaaa").exists()


def test_stage_rejects_branch_that_changed_during_build(release_api, tmp_path):
    api_base, built_commit = release_api
    branch = "codex/release-readiness-a2"
    current_commit = "b" * 40
    ReleaseServer.routes[
        f"/repos/basistech-llc/temperature-bot/commits/{branch.replace('/', '%2F')}"
    ] = (
        "application/json",
        json.dumps(
            {"sha": current_commit, "html_url": f"{api_base}/commit/{current_commit}"}
        ).encode(),
    )
    package = _package(tmp_path / "candidate", "1.0a1", built_commit)
    manifest = verify_package(package)
    target = DeploymentTarget(
        name="staging",
        root=tmp_path / "install",
        quiesce_units=(),
        resume_units=(),
        health=(),
    )
    candidate = UpdateCandidate(
        package=package,
        manifest=manifest,
        source_url=f"{api_base}/commit/{built_commit}",
        source_label=f"branch:{branch}",
        allow_same_version=True,
        branch=branch,
    )

    with pytest.raises(ValueError, match="changed .* during build"):
        _stage_candidate(
            candidate,
            target,
            UpdateOptions(
                branch=branch,
                api_base=api_base,
                create_venv=False,
            ),
        )

    assert not (target.root / "releases").exists()


def test_builder_output_copy_rejects_symlinks(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    target = _source(tmp_path, "target.whl", b"wheel")
    (artifacts / "candidate.whl").symlink_to(target)
    directory_fd = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(OSError):
            _copy_builder_output(
                directory_fd,
                "candidate.whl",
                tmp_path / "trusted.whl",
                os.getuid(),
            )
    finally:
        os.close(directory_fd)

    assert not (tmp_path / "trusted.whl").exists()


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


def test_branch_and_commit_selectors_resolve_to_immutable_commit(release_api):
    api_base, commit = release_api

    branch = resolve_source_selection(
        "basistech-llc/temperature-bot",
        "branch",
        "codex/release-readiness-a2",
        api_base=api_base,
    )
    exact = resolve_source_selection(
        "basistech-llc/temperature-bot",
        "commit",
        commit[:12],
        api_base=api_base,
    )

    assert branch.commit == commit
    assert exact.commit == commit
    assert branch.kind == "branch"
    assert exact.kind == "commit"


def test_source_selectors_are_mutually_exclusive():
    with pytest.raises(ValueError, match="mutually exclusive"):
        UpdateOptions(branch="main", commit="a" * 40)


def test_source_selectors_are_restricted_to_staging(tmp_path):
    target = DeploymentTarget(
        name="production",
        root=tmp_path / "production",
        quiesce_units=(),
        resume_units=(),
        health=(),
    )

    with pytest.raises(ValueError, match="restricted to staging"):
        run_update(target, UpdateOptions(branch="main"))


def test_source_commit_is_built_into_verified_deployment_package(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    commit = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    uv = shutil.which("uv")
    assert uv is not None
    selection = SourceSelection(
        kind="commit",
        value=commit,
        commit=commit,
        html_url=f"https://github.com/basistech-llc/temperature-bot/commit/{commit}",
    )

    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    package, manifest = build_source_package(
        selection,
        first,
        SourceBuildOptions(
            repository="basistech-llc/temperature-bot",
            clone_url=repo_root.as_uri(),
            uv=uv,
            python="3.12",
            build_user=pwd.getpwuid(os.getuid()).pw_name,
        ),
    )
    repeated_package, repeated_manifest = build_source_package(
        selection,
        second,
        SourceBuildOptions(
            repository="basistech-llc/temperature-bot",
            clone_url=repo_root.as_uri(),
            uv=uv,
            python="3.12",
            build_user=pwd.getpwuid(os.getuid()).pw_name,
        ),
    )

    assert package.is_file()
    assert package.with_suffix(".zip.sha256").is_file()
    assert manifest.commit == commit
    assert not manifest.dirty
    assert repeated_manifest == manifest
    assert repeated_package.read_bytes() == package.read_bytes()
    assert all(
        not path.stat().st_mode & 0o222
        for path in (first / "checkout").rglob("*")
        if path.is_file()
    )


def test_root_staging_does_not_execute_candidate_code(tmp_path):
    version = "1.0.0a2"
    sentinel = tmp_path / "candidate-executed"
    wheel = _wheel_with_import_side_effect(tmp_path, version, sentinel)
    requirements = _source(tmp_path, "runtime.txt", b"")
    package = tmp_path / "deployment.zip"
    build_package(
        package,
        PackageIdentity(
            version=version,
            commit="a" * 40,
            built_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
            requires_python=">=3.12",
            flyway_version="12.8.1",
        ),
        [
            PayloadSource(
                source=wheel,
                path=f"wheel/{wheel.name}",
                role="wheel",
            ),
            PayloadSource(
                source=requirements,
                path="requirements/runtime.txt",
                role="requirements",
            ),
        ],
    )

    uv = shutil.which("uv")
    assert uv is not None
    installed = install_package(package, tmp_path / "root", uv=uv, python="3.12")

    lib64 = installed.release_directory / "venv/lib64"
    if not lib64.exists():
        lib64.symlink_to("lib", target_is_directory=True)
    _verify_environment(installed.release_directory, verify_package(package))

    assert not sentinel.exists()


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


def test_source_update_allows_new_commit_at_same_version(tmp_path):
    active = verify_package(_package(tmp_path / "active", "1.0", "a" * 40))
    candidate = verify_package(_package(tmp_path / "candidate", "1.0", "b" * 40))

    assert update_required(active, candidate, allow_same_version=True)
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
        with pytest.raises(ValueError, match="control mode is read-only"):
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


def test_complete_runtime_policy_rejects_integration_drift():
    endpoint = HealthEndpoint(
        url="http://127.0.0.1/api/v1/version",
        instance="air-stage",
        control_mode="live",
        database_identity="air-stage",
        scheduler_mode="enabled",
        integrations=IntegrationModes(
            ae200=False, hubitat=False, airthings=False, aqicn=False
        ),
    )
    payload = RuntimeHealth(
        version="1.0",
        commit="a" * 40,
        instance="air-stage",
        control_mode="live",
        database_identity="air-stage",
        scheduler_mode="enabled",
        integrations=IntegrationModes(
            ae200=False, hubitat=False, airthings=False, aqicn=True
        ),
    )

    with pytest.raises(ValueError, match="integration modes"):
        _check_runtime_policy(endpoint, payload)


def test_activation_refuses_systemd_unit_drift_before_stopping_units(tmp_path):
    active_package = _package(tmp_path / "active", "0.9", "a" * 40)
    candidate_package = _package(tmp_path / "candidate", "1.0", "b" * 40)
    active = verify_package(active_package)
    candidate = verify_package(candidate_package)
    root = tmp_path / "root"
    installed = install_package(
        active_package, root, create_venv=False, activate=True
    )
    command, state = _systemctl(tmp_path)
    (tmp_path / "installed-units/web.service").write_text(
        "[Service]\nExecStart=false\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="systemd unit definitions differ"):
        activate_schema_neutral_release(
            candidate_package,
            _activation_target(root, 1),
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
    assert json.loads(state.read_text())["events"] == []


def test_activation_refuses_systemd_drop_ins_before_stopping_units(tmp_path):
    active_package = _package(tmp_path / "active", "0.9", "a" * 40)
    candidate_package = _package(tmp_path / "candidate", "1.0", "b" * 40)
    active = verify_package(active_package)
    candidate = verify_package(candidate_package)
    root = tmp_path / "root"
    installed = install_package(
        active_package, root, create_venv=False, activate=True
    )
    command, state = _systemctl(tmp_path)
    systemd_state = json.loads(state.read_text())
    systemd_state["drop_in_paths"] = "/etc/systemd/system/web.service.d/override.conf"
    state.write_text(json.dumps(systemd_state), encoding="utf-8")

    with pytest.raises(ValueError, match="unreviewed drop-ins"):
        activate_schema_neutral_release(
            candidate_package,
            _activation_target(root, 1),
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
    assert json.loads(state.read_text())["events"] == []
