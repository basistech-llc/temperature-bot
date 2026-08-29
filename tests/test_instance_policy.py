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


def _developer_environment(monkeypatch, root: Path, instance: str = "slg1") -> None:
    monkeypatch.setenv(INSTANCE_ENV, instance)
    monkeypatch.setenv(CONTROL_MODE_ENV, "simulator")
    monkeypatch.setenv(DATABASE_IDENTITY_ENV, instance)
    monkeypatch.setenv(DATABASE_ROOT_ENV, str(root))
    monkeypatch.setenv("DB_PATH", str(root / "temperature-bot.db"))
    monkeypatch.setenv(SCHEDULER_MODE_ENV, "disabled")
    for name in SIMULATOR_ENVIRONMENTS:
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
