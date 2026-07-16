"""Deterministic device classification from discovery metadata."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DEVICE_TYPE_SENSOR = "SENSOR"
DEVICE_TYPE_FAN = "FAN"
DEVICE_TYPE_CONTROL = "CONTROL"
DEVICE_TYPE_INTERNAL = "INTERNAL"
DEVICE_TYPE_ERV = "ERV"
DEVICE_TYPE_FCU = "FCU"


class HubitatCommand(BaseModel):
    """Command entry returned by Maker API."""

    model_config = ConfigDict(extra="ignore")
    command: str


class HubitatDevice(BaseModel):
    """Maker API fields needed for identity and classification."""

    model_config = ConfigDict(extra="ignore")
    name: str
    id: str | int | None = None
    capabilities: set[str] = Field(default_factory=set)
    commands: list[HubitatCommand] = Field(default_factory=list)


class HubitatControlAttributes(BaseModel):
    """Control attributes returned by the Maker API single-device endpoint."""

    model_config = ConfigDict(extra="ignore")
    level: int | None = Field(default=None, ge=0, le=100)
    switch: Literal["on", "off"] | None = None


class HubitatControlDevice(BaseModel):
    """Typed subset of a Maker API single-device response."""

    model_config = ConfigDict(extra="ignore")
    attributes: HubitatControlAttributes = Field(default_factory=HubitatControlAttributes)


FAN_CAPABILITIES = frozenset({"FanControl"})
CONTROL_CAPABILITIES = frozenset(
    {"Actuator", "Switch", "SwitchLevel", "PushableButton", "DoorControl", "Lock"}
)
SENSOR_CAPABILITIES = frozenset(
    {
        "Sensor",
        "TemperatureMeasurement",
        "MotionSensor",
        "RelativeHumidityMeasurement",
        "IlluminanceMeasurement",
        "ContactSensor",
    }
)
CONTROL_COMMANDS = frozenset(
    {"on", "off", "setLevel", "push", "open", "close", "lock", "unlock"}
)
LEGACY_CONTROL_NAME_MARKERS = (" dimmer ", " color ", " intensity ")
LEGACY_SENSOR_NAME_MARKERS = (" sensor ", " meter ", " ceiling ", " cage ")


def classify_hubitat_device(device: HubitatDevice) -> tuple[str | None, str]:
    """Return the database type and the evidence used to choose it."""
    capabilities = device.capabilities
    commands = {item.command for item in device.commands}
    if match := FAN_CAPABILITIES & capabilities:
        return DEVICE_TYPE_FAN, f"Hubitat capability: {sorted(match)[0]}"
    if match := CONTROL_CAPABILITIES & capabilities:
        return DEVICE_TYPE_CONTROL, f"Hubitat control capability: {sorted(match)[0]}"
    if match := CONTROL_COMMANDS & commands:
        return DEVICE_TYPE_CONTROL, f"Hubitat control command: {sorted(match)[0]}"
    if match := SENSOR_CAPABILITIES & capabilities:
        return DEVICE_TYPE_SENSOR, f"Hubitat sensor capability: {sorted(match)[0]}"
    return DEVICE_TYPE_CONTROL, "Hubitat device without sensor capabilities"


def classify_legacy_hubitat_name(name: str) -> tuple[str | None, str]:
    """Classify historical rows that predate persisted Hubitat metadata."""
    padded_name = f" {name.lower()} "
    if marker := next(
        (item.strip() for item in LEGACY_CONTROL_NAME_MARKERS if item in padded_name),
        None,
    ):
        return DEVICE_TYPE_CONTROL, f"legacy Hubitat control name marker: {marker}"
    if marker := next(
        (item.strip() for item in LEGACY_SENSOR_NAME_MARKERS if item in padded_name),
        None,
    ):
        return DEVICE_TYPE_SENSOR, f"legacy Hubitat sensor name marker: {marker}"
    return DEVICE_TYPE_CONTROL, "legacy Hubitat device without sensor name marker"
