"""Pydantic data contracts shared by the application.

This module is the home for structured application data that crosses module
boundaries:

- Request models are populated by ``flask_pydantic`` route validation and are
  passed into ``rules_engine`` command functions.
- Response models validate data assembled from SQLite rows or external
  services before routes/templates receive JSON-ready dictionaries.

The Flask and Jinja layers still work with mutable mappings today because they
add CSS annotations and other display-only values. Use ``json_ready()`` at those
boundaries instead of ``typing.cast`` so the data is actually validated before it
becomes a mapping.
"""

from enum import StrEnum
from typing import Annotated, Any, Dict, Iterable, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import ae200

# weekdays
MONDAY = 0
TUESDAY = 1
WEDNESDAY = 2
THURSDAY = 3
FRIDAY = 4
SATURDAY = 5
SUNDAY = 6

DriveState = Literal["OFF", "ON"]
FanSpeedName = Literal["AUTO", "LOW", "MID2", "MID1", "HIGH"]

################################################################
## for rules
class Device(BaseModel):
    """Devices as passed to rules engine"""
    device_id: int = Field(description="SQLite3 device_id")
    erv: bool = Field(description="is this an ERV?")
    name: str = Field(description="the name of the device")
    device_type: str | None = Field(default=None, description="Configured device type.")
    rules_enabled: bool = Field(default=True, description="Whether rules may act.")

class RuleResult(BaseModel):
    """Results passed back to Rules Engine"""
    fan_speed: FanSpeedName | None = Field(
        default=None, description="AE-200 fan speed name."
    )
    drive: DriveState | None = Field(default=None, description="AE-200 drive state.")

    @field_validator("fan_speed", mode="before")
    @classmethod
    def normalize_fan_speed(cls, value):
        """Allow rules to use AE-200 protocol names or legacy speed codes."""
        return _rule_name(value, ae200.FAN_SPEEDS, ae200.FAN_SPEED_NAMES, "fan_speed")

    @field_validator("drive", mode="before")
    @classmethod
    def normalize_drive(cls, value):
        """Allow rules to use ON/OFF names or legacy drive codes."""
        return _rule_name(value, ae200.DRIVES, ae200.DRIVE_NAMES, "drive")


def _rule_code(value, names_to_codes: dict[str, int], field_name: str):
    if value is None or isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        if not normalized:
            return None
        if normalized in names_to_codes:
            return names_to_codes[normalized]
        try:
            return int(normalized)
        except ValueError as exc:
            raise ValueError(f"unknown {field_name}: {value!r}") from exc
    return value


def _rule_name(
    value,
    codes_to_names: dict[int, str],
    names_to_codes: dict[str, int],
    field_name: str,
):
    if value is None:
        return None
    if isinstance(value, int):
        if value in codes_to_names:
            return codes_to_names[value]
        raise ValueError(f"unknown {field_name}: {value!r}")
    if isinstance(value, str):
        normalized = value.strip().upper()
        if not normalized:
            return None
        if normalized in names_to_codes:
            return normalized
        try:
            code = int(normalized)
        except ValueError as exc:
            raise ValueError(f"unknown {field_name}: {value!r}") from exc
        if code in codes_to_names:
            return codes_to_names[code]
        raise ValueError(f"unknown {field_name}: {value!r}")
    return value


class ApplicationMetadata(BaseModel):
    """Runtime metadata displayed in the site footer."""

    app_version: str = Field(description="Application version string.")
    deployment_date: str = Field(description="Local mtime of the app directory.")
    deployment_year: int = Field(description="Year from the deployment date.")
    git_branch_url: str = Field(description="GitHub URL for the deployed branch.")
    git_commit: str = Field(description="Git commit for the deployed checkout.")


def _optional_stripped(value):
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _optional_upper(value):
    value = _optional_stripped(value)
    if isinstance(value, str):
        return value.upper()
    return value

################################################################



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


class MapPoint(BaseModel):
    """One point in image-relative map coordinates."""

    x: float
    y: float


class RoomMap(BaseModel):
    """Display metadata for drawing a room polygon on the map."""

    polygon: list[MapPoint] | None = None
    color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Hex RGB fill/stroke color for the room polygon.",
    )


class Room(BaseModel):
    """Room metadata stored in the database and returned by the API."""

    room_id: int | None = None
    room_name: str | None = Field(default=None, min_length=1)
    fcu_device_id: int | None = Field(
        default=None,
        description="FCU that owns this room, when assigned.",
    )
    map: RoomMap | None = None


class RoomCreate(BaseModel):
    """Client-settable fields for creating a room."""

    model_config = ConfigDict(extra="forbid")

    room_name: str = Field(min_length=1)
    map: RoomMap | None = None


class RoomPatch(BaseModel):
    """Client-settable fields for updating a room."""

    model_config = ConfigDict(extra="forbid")

    room_name: str | None = Field(default=None, min_length=1)
    map: RoomMap | None = None


class RoomListResponse(BaseModel):
    """Alphabetized persisted room topology returned by the API."""

    rooms: list[Room]


class RoomTopologyReconciliation(BaseModel):
    """Summary of an idempotent FCU-room topology reconciliation."""

    fcu_count: int
    rooms_created: int
    rooms_claimed: int
    assignments_changed: int


class DatabaseColumn(BaseModel):
    """One SQLite column definition used by startup schema validation."""

    table_name: str
    column_name: str
    column_type: str
    not_null: bool
    default_value: str | None = None
    primary_key: bool


class DatabaseIndex(BaseModel):
    """One SQLite index used by startup schema validation."""

    table_name: str
    index_name: str
    is_unique: bool


class DatabaseSchemaSnapshot(BaseModel):
    """Application schema objects discovered from a SQLite database."""

    tables: list[str] = Field(default_factory=list)
    columns: list[DatabaseColumn] = Field(default_factory=list)
    indexes: list[DatabaseIndex] = Field(default_factory=list)


class DatabaseSchemaIssue(BaseModel):
    """One mismatch between the expected and actual database schema."""

    issue_type: str
    object_name: str
    detail: str


class TimeSeries(BaseModel):
    """One chart series for a single device."""

    device_id: int = Field(description="Local device id from the devices table.")
    name: str = Field(description="Display name for the chart series.")
    data: list[tuple[int, float | None]] = Field(
        description="Ordered (unix time, value) samples; null preserves a data gap."
    )


class TemperatureSeriesResponse(BaseModel):
    """Temperature chart data and availability outside the requested window."""

    series: list[TimeSeries] = Field(default_factory=list)
    has_earlier_data: bool = False
    has_later_data: bool = False


class FcuStateSample(BaseModel):
    """One recorded FCU operating-state sample on the history timeline."""

    timestamp: int
    mode: str | None = None
    drive: str | None = None
    fan_speed: str | None = None


class FcuHistoryResponse(BaseModel):
    """Combined calculated-room, inlet-temperature, and FCU-state history."""

    fcu_device_id: int
    room_id: int
    room_name: str
    temperature_series: list[TimeSeries] = Field(default_factory=list)
    states: list[FcuStateSample] = Field(default_factory=list)


class ChangelogRow(BaseModel):
    """One changelog row returned to the DataTables endpoint."""

    logtime: int | None = None
    ipaddr: str | None = None
    unit: str | None = None
    current_values: Any | None = None
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

    @field_validator("fan_speed", mode="before")
    @classmethod
    def normalize_fan_speed(cls, value):
        """Accept AE-200 speed names while preserving the integer command path."""
        return _rule_code(value, ae200.FAN_SPEED_NAMES, "fan_speed")


class DriveControl(BaseModel):
    """Request body for changing an AE-200 drive state.

    Used by ``POST /api/v1/set_drive`` and by rules that command drive state
    directly. The route layer is responsible for rejecting invalid API payloads;
    the rules layer may construct this model internally after deriving a
    command.
    """

    device_id: int = Field(description="Local device id from the devices table.")
    drive: int = Field(description="Requested AE-200 drive state code.")

    @field_validator("drive", mode="before")
    @classmethod
    def normalize_drive(cls, value):
        """Accept ON/OFF while preserving the integer command path."""
        return _rule_code(value, ae200.DRIVE_NAMES, "drive")


class ModeControl(BaseModel):
    """Request body for changing an AE-200 operation mode."""

    device_id: int = Field(description="Local device id from the devices table.")
    mode: Literal["FAN", "COOL", "DRY", "HEAT", "AUTO"] = Field(
        description="Requested AE-200 operation mode."
    )


class NoteControl(BaseModel):
    """Request body for updating the operator note attached to a device."""

    device_id: int = Field(description="Local device id from the devices table.")
    notes: str | None = Field(description="Replacement note text, or null to clear it.")


class DeviceMetadataControl(BaseModel):
    """Editable metadata stored on the devices table."""

    device_id: int = Field(description="Local device id from the devices table.")
    display_name: str | None = Field(
        default=None,
        description="Optional operator-facing display name override.",
    )
    device_type: str | None = Field(
        default=None,
        description="Optional configured device type such as FCU or ERV.",
    )
    rules_enabled: bool | None = Field(
        default=None,
        description="Whether rules may act on this device.",
    )
    notes: str | None = Field(
        default=None,
        description="Optional operator note.",
    )

    @field_validator("display_name", "notes", mode="before")
    @classmethod
    def normalize_optional_text(cls, value):
        return _optional_stripped(value)

    @field_validator("device_type", mode="before")
    @classmethod
    def normalize_device_type(cls, value):
        return _optional_upper(value)


class SetTempControl(BaseModel):
    """Request body for changing an AE-200 set temperature.

    ``set_temp_c`` is always Celsius. Browser code can display Fahrenheit, but
    conversion must happen before submitting the API request.
    """

    device_id: int = Field(description="Local device id from the devices table.")
    set_temp_c: float = Field(description="Requested set point in degrees Celsius.")


class AutoSetTempControl(BaseModel):
    """Request body for changing AE-200 Auto Heat/Cool setpoints."""

    device_id: int = Field(description="Local device id from the devices table.")
    heat_set_temp_c: float = Field(description="Requested Auto Heat set point in Celsius.")
    cool_set_temp_c: float = Field(description="Requested Auto Cool set point in Celsius.")

    @model_validator(mode="after")
    def validate_range(self):
        if self.heat_set_temp_c >= self.cool_set_temp_c:
            raise ValueError("heat_set_temp_c must be lower than cool_set_temp_c")
        return self


class SetRangeControl(BaseModel):
    """Request body for changing an FCU temperature set range."""

    device_id: int = Field(description="Local device id from the devices table.")
    set_range_low_c: float = Field(description="Lower range end in degrees Celsius.")
    set_range_high_c: float = Field(description="Upper range end in degrees Celsius.")


class FcuSetRange(BaseModel):
    """Persisted FCU temperature range in degrees Celsius."""

    device_id: int = Field(description="Local FCU device id from the devices table.")
    set_range_low_c: float
    set_range_high_c: float
    min_set_range_c: float
    updated_at: int | None = None


class DeviceRoomControl(BaseModel):
    """Request body for assigning a device to a room."""

    model_config = ConfigDict(extra="forbid")

    device_id: int = Field(description="Local device id from the devices table.")
    room_id: int | None = Field(description="Room id, or null to clear assignment.")


class FcuTempSourceControl(BaseModel):
    """Request body for one FCU temperature source multiplier."""

    fcu_device_id: int = Field(description="FCU device id from the devices table.")
    source_device_id: int = Field(description="Temperature source device id.")
    multiplier: float = Field(ge=0, description="Nonnegative source weight.")


FcuTempSourceBatchControl = Annotated[
    list[FcuTempSourceControl],
    Field(min_length=1),
]


class FcuTempSourceRow(BaseModel):
    """One candidate source shown in the FCU temperature-source popup."""

    source_device_id: int
    device_name: str
    room_id: int | None = None
    room_name: str | None = None
    is_fcu_self: bool = False
    temp10x: int | None = None
    age_seconds: int | None = None
    is_stale: bool = False
    multiplier: float = 0
    included: bool = False


class FcuTempSourcesResponse(BaseModel):
    """All temperature-source multiplier rows for one FCU."""

    fcu_device_id: int
    stale_seconds: int
    sources: list[FcuTempSourceRow]


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
    display_name: str | None = Field(
        default=None,
        description="Operator-facing display name override.",
    )
    device_type: str | None = Field(
        default=None,
        description="Configured or inferred device type.",
    )
    log_id: int | None = Field(default=None, description="Latest devlog row id.")
    logtime: int | None = Field(default=None, description="Unix timestamp for the row.")
    duration: int | None = Field(default=None, description="Run-length duration in seconds.")
    temp10x: int | None = Field(default=None, description="Temperature in Celsius tenths.")
    calculated_temp10x: int | None = Field(
        default=None,
        description="Weighted calculated room temperature in Celsius tenths.",
    )
    calculated_humidity: float | None = Field(
        default=None,
        description="Equal-weight calculated room humidity percent.",
    )
    temp_source_stale_seconds: int | None = Field(
        default=None,
        description="Age cutoff for excluding stale calculated-temperature sources.",
    )
    notes: str | None = Field(default=None, description="Operator note from the devices table.")
    aqi_mon: bool | None = Field(
        default=None,
        description="Whether the device is configured as an indoor air-quality monitor.",
    )
    room_id: int | None = Field(default=None, description="Assigned room id.")
    room_name: str | None = Field(default=None, description="Assigned room name.")
    disabled_until: int | None = Field(
        default=None,
        description="Unix timestamp until which automation is disabled.",
    )
    rules_enabled: bool = Field(
        default=True,
        description="Whether rules may act on this device.",
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
    set_temp_c: float | None = Field(
        default=None,
        description="AE-200 single set temperature in degrees Celsius.",
    )
    cool_set_temp_c: float | None = Field(
        default=None,
        description="AE-200 dual-setpoint Cool temperature in degrees Celsius.",
    )
    heat_set_temp_c: float | None = Field(
        default=None,
        description="AE-200 dual-setpoint Heat temperature in degrees Celsius.",
    )
    auto_min_c: float | None = Field(
        default=None,
        description="Minimum allowed AE-200 Auto set temperature in degrees Celsius.",
    )
    auto_max_c: float | None = Field(
        default=None,
        description="Maximum allowed AE-200 Auto set temperature in degrees Celsius.",
    )

    set_range_low_c: float | None = Field(
        default=None,
        description="Lower configured FCU set-range end in degrees Celsius.",
    )
    set_range_high_c: float | None = Field(
        default=None,
        description="Upper configured FCU set-range end in degrees Celsius.",
    )
    min_set_range_c: float | None = Field(
        default=None,
        description="System-wide minimum FCU set-range width in degrees Celsius.",
    )


class RoomMatrixGroup(BaseModel):
    """One room section in the main-page sensor matrix."""

    room_id: int | None = None
    room_name: str
    fcu_device_id: int | None = None
    calculated_temp10x: int | None = None
    calculated_humidity: float | None = None
    devices: list[DeviceStatus] = Field(default_factory=list)


class RoomDashboardSensorAttributes(BaseModel):
    """Fresh canonical metrics rendered on a room sensor tile."""

    temperature: float | None = None
    humidity: int | None = None


class RoomDashboardSensor(BaseModel):
    """One assigned sensor rendered by a canonical room dashboard."""

    id: int
    name: str
    display_name: str
    offline: bool = False
    attributes: RoomDashboardSensorAttributes


class PresenceState(StrEnum):
    """Room presence result, including absence of trustworthy observations."""

    PRESENT = "present"
    ABSENT = "absent"
    STALE = "stale"
    UNKNOWN = "unknown"


class PresenceEvent(BaseModel):
    """One stored observation attributed to the device's room at that time."""

    presence_event_id: int
    device_id: int
    device_name: str
    room_id: int | None = None
    room_name: str | None = None
    observed_at: int
    present: bool


class RoomPresence(BaseModel):
    """Current presence result for one canonical room."""

    room_id: int
    room_name: str
    state: PresenceState
    observed_at: int | None = None
    source_device_ids: list[int] = Field(default_factory=list)


class RoomPresenceResponse(BaseModel):
    """Current presence for all canonical rooms."""

    stale_after_seconds: int
    rooms: list[RoomPresence]


class PresenceHistoryResponse(BaseModel):
    """Presence observations retained with their room-at-observation identity."""

    events: list[PresenceEvent]


class TableUpdateSummary(BaseModel):
    """Oldest timestamp represented by the data currently shown in a table."""

    oldest_update_at: int
    oldest_update_datetime: str
    oldest_update_age: str
    source_device_name: str | None = None
    label: str


def json_ready(model: BaseModel) -> Dict[str, Any]:
    """Dump a validated model to the mapping shape used by routes/templates.

    ``exclude_none=True`` intentionally omits optional fields whose source data
    is unavailable instead of serializing those fields as explicit nulls.
    """
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def json_ready_list(models: Iterable[BaseModel]) -> list[Dict[str, Any]]:
    """Dump validated models to JSON-ready mappings."""
    return [json_ready(model) for model in models]
