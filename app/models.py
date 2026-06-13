"""Pydantic data contracts shared by the application.

This module is the home for structured application data that crosses module
boundaries:

- Request models are populated by ``flask_pydantic`` route validation and are
  passed into ``rules_engine`` command functions.
- Response models validate data assembled from SQLite rows or external
  services before routes/templates receive JSON-ready dictionaries.

The Flask and Jinja layers still work with mutable mappings today because they
add display-only fields such as ``display_name`` and CSS annotations. Use
``json_ready()`` at those boundaries instead of ``typing.cast`` so the data is
actually validated before it becomes a mapping.
"""

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field


class AqiSummary(BaseModel):
    """Decoded outdoor AQI value.

    Created from ``airquality.aqi_decode()`` and embedded in weather API
    responses plus the air-quality page's outdoor row.
    """

    value: int = Field(description="Numeric Air Quality Index value.")
    name: str = Field(description="Human-readable AQI category.")
    color_name: str = Field(description="EPA AQI color category name.")
    color: str = Field(description="Display hex color for the AQI category.")


class SpeedControl(BaseModel):
    """Request body for changing an AE-200 fan speed.

    Used by ``POST /api/v1/set_fan_speed`` and by rules that command fan speed
    directly. ``device_id`` is the local ``devices.device_id`` value.
    """

    device_id: int = Field(description="Local device id from the devices table.")
    fan_speed: int = Field(description="Requested AE-200 fan speed code.")


class DriveControl(BaseModel):
    """Request body for changing an AE-200 drive state.

    Used by ``POST /api/v1/set_drive`` and by rules that command drive state
    directly. The route layer is responsible for rejecting invalid API payloads;
    the rules layer may construct this model internally after deriving a
    command.
    """

    device_id: int = Field(description="Local device id from the devices table.")
    drive: int = Field(description="Requested AE-200 drive state code.")


class NoteControl(BaseModel):
    """Request body for updating the operator note attached to a device."""

    device_id: int = Field(description="Local device id from the devices table.")
    notes: str | None = Field(description="Replacement note text, or null to clear it.")


class SetTempControl(BaseModel):
    """Request body for changing an AE-200 set temperature.

    ``set_temp_c`` is always Celsius. Browser code can display Fahrenheit, but
    conversion must happen before submitting the API request.
    """

    device_id: int = Field(description="Local device id from the devices table.")
    set_temp_c: float = Field(description="Requested set point in degrees Celsius.")


class DeviceStatus(BaseModel):
    """Latest database status row plus derived display annotations.

    ``db.get_device_status()`` and ``db.get_all_device_aqi()`` build this model
    from the newest ``devlog`` row joined with ``devices``. The dumped mapping is
    consumed by JSON endpoints and Jinja templates.

    ``status`` contains decoded vendor payloads from ``devlog.status_json``.
    Extra fields are allowed because integrations add device-specific keys and
    the database layer adds derived flags such as ``has_co2`` and ``drive``.
    """

    model_config = ConfigDict(extra="allow")

    device_id: int = Field(description="Local device id from the devices table.")
    device_name: str = Field(description="Canonical device name from the database.")
    log_id: int | None = Field(default=None, description="Latest devlog row id.")
    logtime: int | None = Field(default=None, description="Unix timestamp for the row.")
    duration: int | None = Field(default=None, description="Run-length duration in seconds.")
    temp10x: int | None = Field(default=None, description="Temperature in Celsius tenths.")
    notes: str | None = Field(default=None, description="Operator note from the devices table.")
    disabled_until: int | None = Field(
        default=None,
        description="Unix timestamp until which automation is disabled.",
    )
    ae200_device_id: int | None = Field(
        default=None,
        description="AE-200 unit id linked to this local device, when present.",
    )
    status: Dict[str, Any] | None = Field(
        default=None,
        description="Decoded vendor payload from devlog.status_json.",
    )
    age: str | None = Field(
        default=None,
        description="Human-readable age string computed from logtime and duration.",
    )
    has_illuminance: bool | None = Field(
        default=None,
        description="Whether the latest status has an illuminance value.",
    )


def json_ready(model: BaseModel) -> Dict[str, Any]:
    """Dump a validated model to the mapping shape used by routes/templates.

    ``exclude_none=True`` intentionally omits optional fields whose source data
    is unavailable instead of serializing those fields as explicit nulls.
    """
    return model.model_dump(exclude_none=True)
