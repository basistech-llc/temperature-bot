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

from typing import Any, Dict, Iterable

from pydantic import BaseModel, ConfigDict, Field


class StatusPayload(BaseModel):
    """Decoded integration payload from ``devlog.status_json``.

    Integrations own the nested vendor keys, so this model deliberately allows
    extra fields while still making the app-owned boundary explicit.
    """

    model_config = ConfigDict(extra="allow")


class RoomConfig(BaseModel):
    """Static dashboard configuration for one room."""

    model_config = ConfigDict(frozen=True)

    url: str = Field(description="Dashboard route for the room.")
    ervs: list[str] = Field(default_factory=list, description="AE-200 ERV names.")
    fans: list[str] = Field(default_factory=list, description="AE-200 fan names.")
    sensors: list[str] = Field(default_factory=list, description="Hubitat sensor names.")
    tv_control: bool = Field(default=False, description="Whether to render TV controls.")
    dimmer_id: str | None = Field(default=None, description="Hubitat dimmer device id.")
    wall_inner_id: str | None = Field(default=None, description="Inner wall light device id.")
    wall_outer_id: str | None = Field(default=None, description="Outer wall light device id.")


class TimeSeries(BaseModel):
    """One chart series for a single device."""

    device_id: int = Field(description="Local device id from the devices table.")
    name: str = Field(description="Display name for the chart series.")
    data: list[tuple[int, float]] = Field(description="Ordered (unix time, value) samples.")


class ChangelogRow(BaseModel):
    """One changelog row returned to the DataTables endpoint."""

    logtime: int | None = None
    ipaddr: str | None = None
    unit: str | None = None
    new_value: Any | None = None
    agent: str | None = None
    comment: str | None = None
    age: str | None = None


class ChangelogResponse(BaseModel):
    """Paginated changelog response for ``/api/v1/changelog``."""

    model_config = ConfigDict(populate_by_name=True)

    draw: int
    records_total: int = Field(alias="recordsTotal")
    records_filtered: int = Field(alias="recordsFiltered")
    data: list[ChangelogRow]


class WeatherStation(BaseModel):
    """Current weather observation from one station."""

    temperature: float | int | None = None
    conditions: str = "Unknown"
    icon: str = ""
    station_name: str = ""


class WeatherData(BaseModel):
    """Weather payload returned by the app weather endpoint."""

    model_config = ConfigDict(extra="forbid")

    stations: list[WeatherStation] = Field(default_factory=list)
    forecast: list[Dict[str, Any]] = Field(default_factory=list)
    daily: list[Dict[str, Any]] = Field(default_factory=list)


class AirMetricThreshold(BaseModel):
    """Threshold rule for an indoor air-quality metric."""

    limit: float
    score: int
    label: str


class AirMetricRange(BaseModel):
    """Range rule for metrics scored by acceptable bands."""

    problem_min: float
    problem_max: float
    elevated_min: float
    elevated_max: float


class AirMetricRule(BaseModel):
    """Scoring configuration for one indoor air-quality metric."""

    short_name: str
    thresholds: list[AirMetricThreshold] = Field(default_factory=list)
    ranges: AirMetricRange | None = None


class AirMetricScore(BaseModel):
    """Scored indoor air-quality reading."""

    severity_score: int
    label: str
    short_name: str

    def as_tuple(self) -> tuple[int, str, str]:
        """Return the historical tuple shape used by existing callers."""
        return (self.severity_score, self.label, self.short_name)


class AirQualityAnnotation(BaseModel):
    """Template annotations derived from indoor air-quality readings."""

    aq_classes: dict[str, str] = Field(default_factory=dict)


class AqiSummary(BaseModel):
    """Decoded outdoor AQI value.

    Created from ``airquality.aqi_decode()`` and embedded in weather API
    responses plus the air-quality page's outdoor row.
    """

    value: int = Field(description="Numeric Air Quality Index value.")
    name: str = Field(description="Human-readable AQI category.")
    color_name: str = Field(description="EPA AQI color category name.")
    color: str = Field(description="Display hex color for the AQI category.")


class AqiWeatherResponse(BaseModel):
    """Combined outdoor AQI and weather payload."""

    aqi: AqiSummary
    weather: WeatherData | Dict[str, Any]


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


class CommandResponse(BaseModel):
    """Successful command response returned by control endpoints."""

    model_config = ConfigDict(extra="allow")

    status: str = "ok"
    device_id: int | None = None
    level: int | None = None
    light: str | None = None
    state: str | None = None
    direction: str | None = None


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
    status: StatusPayload | None = Field(
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
    mode: str | None = Field(
        default=None,
        description="AE-200 operation mode promoted from status.Mode, when present.",
    )


def json_ready(model: BaseModel) -> Dict[str, Any]:
    """Dump a validated model to the mapping shape used by routes/templates.

    ``exclude_none=True`` intentionally omits optional fields whose source data
    is unavailable instead of serializing those fields as explicit nulls.
    """
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def json_ready_list(models: Iterable[BaseModel]) -> list[Dict[str, Any]]:
    """Dump validated models to JSON-ready mappings."""
    return [json_ready(model) for model in models]
