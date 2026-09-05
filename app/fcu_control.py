"""Typed FCU command contract shared by routes and the rules engine."""

from collections.abc import Hashable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import ae200


def _control_code(value, names_to_codes: dict[str, int], field_name: str):
    if value is None or isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in names_to_codes:
            return names_to_codes[normalized]
        try:
            return int(normalized)
        except ValueError as error:
            raise ValueError(f"unknown {field_name}: {value!r}") from error
    return value


class FcuStateControl(BaseModel):
    """One atomic FCU drive/fan command; omitted fields remain unchanged."""

    model_config = ConfigDict(extra="forbid")

    device_id: int = Field(description="Local device id from the devices table.")
    drive: int | None = Field(default=None, description="Requested drive state.")
    fan_speed: int | None = Field(default=None, description="Requested fan speed.")

    @field_validator("drive", mode="before")
    @classmethod
    def normalize_drive(cls, value):
        return _control_code(value, ae200.DRIVE_NAMES, "drive")

    @field_validator("fan_speed", mode="before")
    @classmethod
    def normalize_fan_speed(cls, value):
        code = _control_code(value, ae200.FAN_SPEED_NAMES, "fan_speed")
        if code is not None and (
            not isinstance(code, Hashable) or code not in ae200.FAN_SPEEDS
        ):
            raise ValueError(f"unknown fan_speed: {value!r}")
        return code

    @model_validator(mode="after")
    def require_requested_state(self):
        if self.drive is None and self.fan_speed is None:
            raise ValueError("drive or fan_speed is required")
        if self.drive is not None and self.drive not in ae200.DRIVES:
            raise ValueError(f"unknown drive: {self.drive!r}")
        return self
