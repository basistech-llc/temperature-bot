"""AE-200 real-time diagnostics and command-audit routes."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET

from flask import Blueprint, jsonify, render_template, request
from pydantic import BaseModel, Field
from websockets.exceptions import WebSocketException

from . import ae200, ae200_command_log, ae200_notifications
from .api_errors import BadRequest, UpstreamUnavailable, register_error_handlers
from .models import json_ready
from .util import get_config
from .utils.db_utils import with_db_connection

ae200_routes = Blueprint("ae200_diagnostics", __name__)
register_error_handlers(ae200_routes)


class AE200UnitSnapshot(BaseModel):
    """One current controller unit response, preserving every returned field."""

    device_id: str
    name: str
    status: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


class AE200Snapshot(BaseModel):
    """Current read-only view of the configured AE-200 controller."""

    observed_at_ms: int
    controller_host: str
    simulator: bool
    units: list[AE200UnitSnapshot]


@ae200_routes.get("/ae200")
def ae200_page():
    """Render live AE-200 diagnostics, performance, and command history."""
    return render_template("ae200.html", current_page="ae200")


@ae200_routes.get("/api/v1/ae200/status")
def ae200_status():
    """Read the device list and every known current field for each unit."""
    units: list[AE200UnitSnapshot] = []
    try:
        devices = ae200.get_devices()
    except (
        OSError,
        RuntimeError,
        ValueError,
        ET.ParseError,
        WebSocketException,
    ) as error:
        raise UpstreamUnavailable("AE-200 request failed") from error
    for device in devices:
        device_id = str(device["id"])
        try:
            status = {
                str(key): str(value)
                for key, value in ae200.get_device_info(device_id).items()
            }
            units.append(
                AE200UnitSnapshot(
                    device_id=device_id,
                    name=str(device["name"]),
                    status=status,
                )
            )
        except (
            OSError,
            RuntimeError,
            ValueError,
            ET.ParseError,
            WebSocketException,
        ) as error:
            units.append(
                AE200UnitSnapshot(
                    device_id=device_id,
                    name=str(device["name"]),
                    error=f"{type(error).__name__}: {error}",
                )
            )
    snapshot = AE200Snapshot(
        observed_at_ms=time.time_ns() // 1_000_000,
        controller_host=get_config()["ae200"]["host"],
        simulator=ae200.AE200_SIMULATOR,
        units=units,
    )
    return jsonify(json_ready(snapshot))


@ae200_routes.get("/api/v1/ae200/commands")
@with_db_connection
def ae200_commands(conn):
    """Return the latest durable AE-200 command audit records."""
    try:
        limit = int(request.args.get("limit", ae200_command_log.DEFAULT_LIMIT))
        page = ae200_command_log.fetch_recent(conn, limit)
    except ValueError as error:
        raise BadRequest(str(error)) from error
    return jsonify(page.model_dump(mode="json"))


@ae200_routes.get("/api/v1/ae200/notifications")
@with_db_connection
def ae200_notification_events(conn):
    """Return recent unsolicited controller state observations."""
    try:
        limit = int(request.args.get("limit", ae200_notifications.DEFAULT_LIMIT))
        page = ae200_notifications.fetch_recent(conn, limit)
    except ValueError as error:
        raise BadRequest(str(error)) from error
    return jsonify(page.model_dump(mode="json"))
