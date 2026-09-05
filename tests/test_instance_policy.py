"""Fail-closed instance policy and simulator command coverage."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app import hubitat
from app.instance_policy import (
    ControlMode,
    CONTROL_MODE_ENV,
    DEFAULT_POLICY_FILE,
    DATABASE_IDENTITY_ENV,
    DATABASE_ROOT_ENV,
    INSTANCE_ENV,
    InstancePolicy,
    InstanceRole,
    IntegrationModes,
    SCHEDULER_MODE_ENV,
    SchedulerMode,
    SIMULATOR_ENVIRONMENTS,
    load_policy_table,
    load_instance_policy,
)
from app.main import create_app


def _developer_environment(monkeypatch, root: Path, instance: str = "slg1") -> None:
    monkeypatch.setenv(INSTANCE_ENV, instance)
    monkeypatch.setenv(CONTROL_MODE_ENV, "simulator")
    monkeypatch.setenv(DATABASE_IDENTITY_ENV, instance)
    monkeypatch.setenv(DATABASE_ROOT_ENV, str(root))
    monkeypatch.setenv("DB_PATH", str(root / "temperature-bot.db"))
    monkeypatch.setenv(SCHEDULER_MODE_ENV, "disabled")
    for name in SIMULATOR_ENVIRONMENTS:
        monkeypatch.setenv(name, "1")


def _stage_environment(monkeypatch, root: Path) -> None:
    monkeypatch.setenv(INSTANCE_ENV, "air-stage")
    monkeypatch.setenv(CONTROL_MODE_ENV, "live")
    monkeypatch.setenv(DATABASE_IDENTITY_ENV, "air-stage")
    monkeypatch.setenv(DATABASE_ROOT_ENV, str(root))
    monkeypatch.setenv("DB_PATH", str(root / "temperature-bot.db"))
    monkeypatch.setenv(SCHEDULER_MODE_ENV, "enabled")
    for name in SIMULATOR_ENVIRONMENTS:
        monkeypatch.setenv(name, "0")


def test_policy_table_declares_all_deployed_instances():
    table = load_policy_table()

    assert {definition.name for definition in table.instances} == {
        "production",
        "air-stage",
        "slg1",
        "deg1",
        "local-dev-live",
        "local-dev-sim",
    }
    assert table.for_instance("slg1").database_identity == "slg1"
    assert table.for_instance("deg1").database_identity == "deg1"


def test_policy_table_rejects_unsupported_version(tmp_path):
    policy_path = tmp_path / "instance-policy.yaml"
    policy_path.write_text(
        DEFAULT_POLICY_FILE.read_text(encoding="utf-8").replace("version: 1", "version: 2", 1),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="Input should be 1"):
        load_policy_table(policy_path)


def test_policy_rejects_unknown_instance(monkeypatch):
    monkeypatch.setenv(INSTANCE_ENV, "unknown-instance")

    with pytest.raises(ValueError, match="not in the instance policy table"):
        load_instance_policy()


@pytest.mark.parametrize("instance", ("slg1", "deg1"))
def test_developer_policy_allows_both_private_simulator_instances(
    monkeypatch, tmp_path, instance
):
    _developer_environment(monkeypatch, tmp_path, instance)

    policy = load_instance_policy()

    assert policy.instance == instance
    assert policy.role == "developer"
    assert policy.private_database
    assert policy.control_mode == "simulator"


def test_developer_policy_requires_every_simulator(monkeypatch, tmp_path):
    _developer_environment(monkeypatch, tmp_path)
    monkeypatch.delenv("HUBITAT_SIMULATOR")

    with pytest.raises(ValidationError, match="requires AE-200, Hubitat"):
        load_instance_policy()


def test_developer_policy_rejects_database_outside_private_root(monkeypatch, tmp_path):
    private_root = tmp_path / "private"
    _developer_environment(monkeypatch, private_root)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "production.db"))

    with pytest.raises(ValidationError, match="outside private root"):
        load_instance_policy()


def test_developer_policy_rejects_schedulers(monkeypatch, tmp_path):
    _developer_environment(monkeypatch, tmp_path)
    monkeypatch.setenv(SCHEDULER_MODE_ENV, "enabled")

    with pytest.raises(ValidationError, match="cannot run schedulers"):
        load_instance_policy()


@pytest.mark.parametrize(
    ("instance", "control_mode", "simulated"),
    (("local-dev-live", "live", False), ("local-dev-sim", "simulator", True)),
)
def test_local_development_profiles_match_their_policy(
    monkeypatch, tmp_path, instance, control_mode, simulated
):
    monkeypatch.setenv(INSTANCE_ENV, instance)
    monkeypatch.setenv(CONTROL_MODE_ENV, control_mode)
    monkeypatch.setenv(DATABASE_IDENTITY_ENV, instance)
    monkeypatch.setenv(DATABASE_ROOT_ENV, str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "temperature-bot.db"))
    monkeypatch.setenv(SCHEDULER_MODE_ENV, "disabled")
    for name in SIMULATOR_ENVIRONMENTS:
        monkeypatch.setenv(name, "1" if simulated else "0")

    policy = load_instance_policy()

    assert policy.role == "local"
    assert policy.control_mode == control_mode
    assert policy.scheduler_mode == "disabled"
    assert not policy.is_staging()


def test_stage_policy_allows_live_control_with_private_database(monkeypatch, tmp_path):
    _stage_environment(monkeypatch, tmp_path)

    policy = load_instance_policy()

    policy.require_staging_collector()
    assert policy.is_staging()
    assert policy.public_status().control_mode == "live"
    assert not any(policy.integrations.model_dump().values())


def test_live_policy_allows_read_only_simulators():
    policy = InstancePolicy(
        instance="production",
        role=InstanceRole.PRODUCTION,
        control_mode=ControlMode.LIVE,
        database_identity="production",
        database_path=Path("temperature-bot.db"),
        private_database=False,
        scheduler_mode=SchedulerMode.ENABLED,
        integrations=IntegrationModes(
            ae200=False,
            hubitat=False,
            airthings=True,
            aqicn=True,
        ),
    )

    assert policy.integrations.airthings
    assert policy.integrations.aqicn


@pytest.mark.parametrize("integration", ("AE200_SIMULATOR", "HUBITAT_SIMULATOR"))
def test_live_policy_rejects_command_simulators(monkeypatch, integration):
    monkeypatch.setenv(CONTROL_MODE_ENV, "live")
    monkeypatch.setenv(integration, "1")

    with pytest.raises(ValidationError, match="command-bearing integrations"):
        load_instance_policy()


@pytest.mark.parametrize(
    ("change", "message"),
    (
        (("control", "simulator"), "requires live control mode"),
        (("scheduler", "disabled"), "requires its collection scheduler"),
        (("integration", "1"), "cannot simulate command-bearing integrations"),
        (("identity", "production"), "requires matching database identity"),
        (("database", "outside"), "outside private root"),
    ),
)
def test_stage_policy_fails_closed(monkeypatch, tmp_path, change, message):
    _stage_environment(monkeypatch, tmp_path / "private")
    kind, value = change
    if kind == "control":
        monkeypatch.setenv(CONTROL_MODE_ENV, value)
        for name in SIMULATOR_ENVIRONMENTS:
            monkeypatch.setenv(name, "1")
    elif kind == "scheduler":
        monkeypatch.setenv(SCHEDULER_MODE_ENV, value)
    elif kind == "integration":
        monkeypatch.setenv("AE200_SIMULATOR", value)
    elif kind == "identity":
        monkeypatch.setenv(DATABASE_IDENTITY_ENV, value)
    else:
        monkeypatch.setenv("DB_PATH", str(tmp_path / value / "temperature-bot.db"))

    with pytest.raises(ValidationError, match=message):
        load_instance_policy()


def test_stage_http_is_live_and_warns_operator(
    monkeypatch, test_database_conn_with_test_data
):
    conn, device_id, _counts = test_database_conn_with_test_data
    private_root = Path(conn.execute("PRAGMA database_list").fetchone()[2]).parent
    _stage_environment(monkeypatch, private_root)
    monkeypatch.setenv("DB_PATH", str(private_root / "temperature-bot.db"))
    policy = load_instance_policy().model_copy(
        update={"database_path": Path(conn.execute("PRAGMA database_list").fetchone()[2])}
    )
    app = create_app(policy)
    app.config["TESTING"] = True

    with app.test_client() as client:
        assert client.get("/api/v1/status").status_code == 200
        response = client.patch(
            f"/api/v1/devices/{device_id}", json={"display_name": "changed"}
        )
        assert response.status_code == 200
        html = client.get("/").get_data(as_text=True)

    assert "STAGING ENVIRONMENT — This site is live." in html
    assert "All changes will be reflected on the real equipment." in html
    assert '<a href="https://air.basistech.net/">production</a>' in html
    assert conn.execute(
        "SELECT display_name FROM devices WHERE device_id = ?", (device_id,)
    ).fetchone()[0] == "changed"


def test_hubitat_command_is_stateful_inside_simulator(flask_test_client):  # noqa: F811
    command = flask_test_client.post(
        "/api/v1/room/broadway/switch",
        json={"control": "tv-cart-left", "state": "on"},
    )
    assert command.status_code == 200

    status = flask_test_client.get("/api/v1/room/broadway/room_status")
    assert status.status_code == 200
    left = next(control for control in status.json["controls"] if control["key"] == "tv-cart-left")
    assert left["switch"] == "on"
    assert hubitat.get_device_info("618")["attributes"]["switch"] == "on"
