"""Typed, fail-closed runtime policy for deployed instances."""

from __future__ import annotations

import os
import socket
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .airquality import AQICN_SIMULATOR_ENV, aqicn_simulator_enabled
from .airthings import AIRTHINGS_SIMULATOR_ENV, airthings_simulator_enabled
from .ae200 import AE200_SIMULATOR_ENV, ae200_simulator_enabled
from .constants import DB_PATH
from .hubitat import HUBITAT_SIMULATOR_ENV, hubitat_simulator_enabled

INSTANCE_ENV = "TEMPERATURE_BOT_INSTANCE"
CONTROL_MODE_ENV = "TEMPERATURE_BOT_CONTROL_MODE"
DATABASE_IDENTITY_ENV = "TEMPERATURE_BOT_DATABASE_IDENTITY"
DATABASE_ROOT_ENV = "TEMPERATURE_BOT_DATABASE_ROOT"
SCHEDULER_MODE_ENV = "TEMPERATURE_BOT_SCHEDULER_MODE"
DEVELOPER_INSTANCES = frozenset({"slg1", "deg1"})
STAGING_INSTANCES = frozenset({"air-stage"})


class ControlMode(StrEnum):
    """Whether controller commands are live or simulated."""

    LIVE = "live"
    SIMULATOR = "simulator"


class SchedulerMode(StrEnum):
    """Whether this web instance is authorized to run scheduled rules."""

    DISABLED = "disabled"
    ENABLED = "enabled"


class IntegrationModes(BaseModel):
    """Simulator state for every web-facing external integration."""

    model_config = ConfigDict(extra="forbid")

    ae200: bool
    hubitat: bool
    airthings: bool
    aqicn: bool

    def all_simulated(self) -> bool:
        return all(self.model_dump().values())


class InstancePolicy(BaseModel):
    """One validated deployment identity and its control boundary."""

    model_config = ConfigDict(extra="forbid")

    instance: str = Field(min_length=1)
    control_mode: ControlMode
    database_identity: str | None = None
    database_path: Path
    database_root: Path | None = None
    scheduler_mode: SchedulerMode
    integrations: IntegrationModes

    @model_validator(mode="after")
    def validate_policy(self) -> "InstancePolicy":
        if self.control_mode is ControlMode.SIMULATOR:
            if not self.integrations.all_simulated():
                raise ValueError(
                    "simulator control mode requires AE-200, Hubitat, Airthings, "
                    "and AQICN simulators"
                )
        elif self.control_mode is ControlMode.LIVE and (
            self.integrations.ae200 or self.integrations.hubitat
        ):
            raise ValueError(
                "live control mode cannot simulate command-bearing integrations"
            )

        if self.instance in STAGING_INSTANCES:
            if self.control_mode is not ControlMode.LIVE:
                raise ValueError("staging instance requires live control mode")
            self._validate_private_database("staging")
            if self.scheduler_mode is not SchedulerMode.ENABLED:
                raise ValueError("staging instance requires its collection scheduler")

        if self.instance not in DEVELOPER_INSTANCES:
            return self

        if self.control_mode is not ControlMode.SIMULATOR:
            raise ValueError(f"developer instance {self.instance} must be simulator-only")
        self._validate_private_database("developer")
        if self.scheduler_mode is not SchedulerMode.DISABLED:
            raise ValueError(f"developer instance {self.instance} cannot run schedulers")
        return self

    def _validate_private_database(self, kind: str) -> None:
        if self.database_identity != self.instance:
            raise ValueError(
                f"{kind} instance {self.instance} requires matching database identity"
            )
        if self.database_root is None:
            raise ValueError(f"{kind} instance {self.instance} requires a database root")
        database = self.database_path.resolve(strict=False)
        root = self.database_root.resolve(strict=False)
        if not database.is_relative_to(root):
            raise ValueError(f"{kind} database {database} is outside private root {root}")

    def require_staging_collector(self) -> None:
        """Fail closed unless this process is the staging collection plane."""
        if self.instance not in STAGING_INSTANCES:
            raise RuntimeError("AE-200 staging collection requires a staging instance")

    def is_staging(self) -> bool:
        """Return whether this is an approved live staging instance."""
        return self.instance in STAGING_INSTANCES

    def public_status(self) -> "InstanceStatus":
        """Return the non-secret status exposed through the API."""
        return InstanceStatus(
            instance=self.instance,
            control_mode=self.control_mode,
            database_identity=self.database_identity,
            scheduler_mode=self.scheduler_mode,
            integrations=self.integrations,
        )


class InstanceStatus(BaseModel):
    """Machine-readable, non-secret deployment status."""

    model_config = ConfigDict(extra="forbid")

    instance: str
    control_mode: ControlMode
    database_identity: str | None
    scheduler_mode: SchedulerMode
    integrations: IntegrationModes


def load_instance_policy() -> InstancePolicy:
    """Load and validate the process environment once at application startup."""
    return InstancePolicy(
        instance=os.getenv(INSTANCE_ENV) or socket.gethostname(),
        control_mode=ControlMode(
            os.getenv(CONTROL_MODE_ENV, ControlMode.LIVE.value)
        ),
        database_identity=os.getenv(DATABASE_IDENTITY_ENV),
        database_path=Path(os.getenv(DB_PATH, "temperature-bot.db")),
        database_root=(
            Path(value) if (value := os.getenv(DATABASE_ROOT_ENV)) else None
        ),
        scheduler_mode=SchedulerMode(
            os.getenv(SCHEDULER_MODE_ENV, SchedulerMode.DISABLED.value)
        ),
        integrations=IntegrationModes(
            ae200=ae200_simulator_enabled(),
            hubitat=hubitat_simulator_enabled(),
            airthings=airthings_simulator_enabled(),
            aqicn=aqicn_simulator_enabled(),
        ),
    )


SIMULATOR_ENVIRONMENTS = (
    AE200_SIMULATOR_ENV,
    HUBITAT_SIMULATOR_ENV,
    AIRTHINGS_SIMULATOR_ENV,
    AQICN_SIMULATOR_ENV,
)
