"""Fail-closed instance policy and simulator command coverage."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app import hubitat
from app.instance_policy import (
    CONTROL_MODE_ENV,
    DATABASE_IDENTITY_ENV,
    DATABASE_ROOT_ENV,
    INSTANCE_ENV,
    SCHEDULER_MODE_ENV,
    SIMULATOR_ENVIRONMENTS,
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
    monkeypatch.setenv(CONTROL_MODE_ENV, "read-only")
    monkeypatch.setenv(DATABASE_IDENTITY_ENV, "air-stage")
    monkeypatch.setenv(DATABASE_ROOT_ENV, str(root))
    monkeypatch.setenv("DB_PATH", str(root / "temperature-bot.db"))
    monkeypatch.setenv(SCHEDULER_MODE_ENV, "enabled")
    monkeypatch.delenv("AE200_SIMULATOR", raising=False)
    for name in ("HUBITAT_SIMULATOR", "AIRTHINGS_SIMULATOR", "AQICN_SIMULATOR"):
        monkeypatch.setenv(name, "1")


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


def test_stage_policy_allows_live_ae200_reads_with_private_database(
    monkeypatch, tmp_path
):
    _stage_environment(monkeypatch, tmp_path)

    policy = load_instance_policy()

    policy.require_read_only_collector()
    assert policy.public_status().control_mode == "read-only"


@pytest.mark.parametrize(
    ("change", "message"),
    (
        (("instance", "another-stage"), "approved instance"),
        (("scheduler", "disabled"), "requires its collection scheduler"),
        (("ae200", "1"), "requires live AE-200 reads"),
        (("database", "outside"), "outside private root"),
    ),
)
def test_stage_policy_fails_closed(monkeypatch, tmp_path, change, message):
    _stage_environment(monkeypatch, tmp_path / "private")
    kind, value = change
    if kind == "instance":
        monkeypatch.setenv(INSTANCE_ENV, value)
        monkeypatch.setenv(DATABASE_IDENTITY_ENV, value)
    elif kind == "scheduler":
        monkeypatch.setenv(SCHEDULER_MODE_ENV, value)
    elif kind == "ae200":
        monkeypatch.setenv("AE200_SIMULATOR", value)
    else:
        monkeypatch.setenv("DB_PATH", str(tmp_path / value / "temperature-bot.db"))

    with pytest.raises(ValidationError, match=message):
        load_instance_policy()


def test_stage_http_is_read_only(monkeypatch, test_database_conn_with_test_data):
    conn, device_id, _counts = test_database_conn_with_test_data
    private_root = Path(conn.execute("PRAGMA database_list").fetchone()[2]).parent
    _stage_environment(monkeypatch, private_root)
    monkeypatch.setenv("DB_PATH", str(private_root / "temperature-bot.db"))
    policy = load_instance_policy().model_copy(
        update={"database_path": Path(conn.execute("PRAGMA database_list").fetchone()[2])}
    )
    app = create_app(policy)
    app.config["TESTING"] = True

    before = conn.execute(
        "SELECT display_name FROM devices WHERE device_id = ?", (device_id,)
    ).fetchone()[0]
    with app.test_client() as client:
        assert client.get("/api/v1/status").status_code == 200
        for method, path, body in (
            ("POST", "/api/v1/set_drive", {"device_id": device_id, "drive": 1}),
            ("PATCH", f"/api/v1/devices/{device_id}", {"display_name": "changed"}),
            ("GET", "/api/v1/disable-rules?seconds=3600", None),
        ):
            response = client.open(path, method=method, json=body)
            assert response.status_code == 403
            assert response.get_json()["code"] == "read_only"
        html = client.get("/").get_data(as_text=True)

    assert "READ ONLY — air-stage reads live AE-200 data" in html
    assert '<a href="https://air.basistech.net/">production</a>' in html
    assert conn.execute(
        "SELECT display_name FROM devices WHERE device_id = ?", (device_id,)
    ).fetchone()[0] == before


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
