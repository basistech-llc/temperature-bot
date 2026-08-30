"""Typed, fail-closed runtime policy for deployed instances."""

from __future__ import annotations

import os
import socket
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .airquality import AQICN_SIMULATOR_ENV, aqicn_simulator_enabled
from .airthings import AIRTHINGS_SIMULATOR_ENV, airthings_simulator_enabled
from .ae200 import AE200_SIMULATOR_ENV, ae200_simulator_enabled
from .constants import DB_PATH
from .hubitat import HUBITAT_SIMULATOR_ENV, hubitat_simulator_enabled

INSTANCE_ENV = "TEMPERATURE_BOT_INSTANCE"
POLICY_FILE_ENV = "TEMPERATURE_BOT_INSTANCE_POLICY"
CONTROL_MODE_ENV = "TEMPERATURE_BOT_CONTROL_MODE"
DATABASE_IDENTITY_ENV = "TEMPERATURE_BOT_DATABASE_IDENTITY"
DATABASE_ROOT_ENV = "TEMPERATURE_BOT_DATABASE_ROOT"
SCHEDULER_MODE_ENV = "TEMPERATURE_BOT_SCHEDULER_MODE"
DEFAULT_POLICY_FILE = Path(__file__).with_name("instance_policy.yaml")


class ControlMode(StrEnum):
    """Whether controller commands are live or simulated."""

    LIVE = "live"
    SIMULATOR = "simulator"


class SchedulerMode(StrEnum):
    """Whether this web instance is authorized to run scheduled rules."""

    DISABLED = "disabled"
    ENABLED = "enabled"


class InstanceRole(StrEnum):
    """Operational role used to apply the generic instance invariants."""

    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPER = "developer"


class IntegrationModes(BaseModel):
    """Simulator state for every web-facing external integration."""

    model_config = ConfigDict(extra="forbid")

    ae200: bool
    hubitat: bool
    airthings: bool
    aqicn: bool

    def all_simulated(self) -> bool:
        return all(self.model_dump().values())


class InstanceDefinition(BaseModel):
    """One declarative row from the instance policy table."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    role: InstanceRole
    control_mode: ControlMode
    scheduler_mode: SchedulerMode
    database_identity: str | None = None
    private_database: bool
    integrations: IntegrationModes


class InstancePolicyTable(BaseModel):
    """Validated YAML policy table."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    instances: list[InstanceDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_names(self) -> "InstancePolicyTable":
        names = [definition.name for definition in self.instances]
        if len(names) != len(set(names)):
            raise ValueError("instance policy names are not unique")
        return self

    def for_instance(self, name: str) -> InstanceDefinition:
        """Return one row, failing closed for an unknown instance."""
        for definition in self.instances:
            if definition.name == name:
                return definition
        raise ValueError(f"instance {name!r} is not in the instance policy table")


class InstancePolicy(BaseModel):
    """One validated deployment identity and its control boundary."""

    model_config = ConfigDict(extra="forbid")

    instance: str = Field(min_length=1)
    role: InstanceRole
    control_mode: ControlMode
    database_identity: str | None = None
    database_path: Path
    database_root: Path | None = None
    private_database: bool
    scheduler_mode: SchedulerMode
    integrations: IntegrationModes

    @model_validator(mode="after")
    def validate_policy(self) -> "InstancePolicy":
        self._validate_integration_mode()
        self._validate_database_policy()
        self._validate_role_policy()
        return self

    def _validate_integration_mode(self) -> None:
        if self.control_mode is ControlMode.SIMULATOR:
            if not self.integrations.all_simulated():
                raise ValueError(
                    "simulator control mode requires AE-200, Hubitat, Airthings, "
                    "and AQICN simulators"
                )
        elif self.control_mode is ControlMode.LIVE and any(
            self.integrations.model_dump().values()
        ):
            raise ValueError("live control mode cannot mix simulator integrations")

    def _validate_database_policy(self) -> None:
        if (
            self.role in {InstanceRole.STAGING, InstanceRole.DEVELOPER}
            and not self.private_database
        ):
            raise ValueError(
                f"{self.role.value} instance {self.instance} requires a private database"
            )
        if self.private_database:
            self._validate_private_database(self.role.value)

    def _validate_role_policy(self) -> None:
        if self.role is InstanceRole.PRODUCTION:
            if self.control_mode is not ControlMode.LIVE:
                raise ValueError("production instance requires live control mode")

        if self.role is InstanceRole.STAGING:
            if self.control_mode is not ControlMode.LIVE:
                raise ValueError("staging instance requires live control mode")
            if self.scheduler_mode is not SchedulerMode.ENABLED:
                raise ValueError("staging instance requires its collection scheduler")

        if self.role is InstanceRole.DEVELOPER:
            if self.control_mode is not ControlMode.SIMULATOR:
                raise ValueError(f"developer instance {self.instance} must be simulator-only")
            if self.scheduler_mode is not SchedulerMode.DISABLED:
                raise ValueError(f"developer instance {self.instance} cannot run schedulers")

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
        if self.role is not InstanceRole.STAGING:
            raise RuntimeError("AE-200 staging collection requires a staging instance")

    def is_staging(self) -> bool:
        """Return whether this is the approved live staging instance."""
        return self.role is InstanceRole.STAGING

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


def _policy_table_path() -> Path:
    return Path(os.getenv(POLICY_FILE_ENV, str(DEFAULT_POLICY_FILE)))


def load_policy_table(path: Path | None = None) -> InstancePolicyTable:
    """Load and validate the declarative policy table."""
    policy_path = path or _policy_table_path()
    try:
        with policy_path.open("r", encoding="utf-8") as policy_file:
            raw_policy = yaml.safe_load(policy_file)
    except FileNotFoundError as exc:
        raise ValueError(f"instance policy file not found: {policy_path}") from exc
    return InstancePolicyTable.model_validate(raw_policy)


def load_instance_policy() -> InstancePolicy:
    """Load and validate the process environment against the policy table."""
    instance = os.getenv(INSTANCE_ENV) or socket.gethostname()
    definition = load_policy_table().for_instance(instance)
    database_root = os.getenv(DATABASE_ROOT_ENV)
    policy = InstancePolicy(
        instance=definition.name,
        role=definition.role,
        control_mode=ControlMode(
            os.getenv(CONTROL_MODE_ENV, definition.control_mode.value)
        ),
        database_identity=os.getenv(
            DATABASE_IDENTITY_ENV, definition.database_identity
        ),
        database_path=Path(os.getenv(DB_PATH, "temperature-bot.db")),
        database_root=Path(database_root) if database_root else None,
        private_database=definition.private_database,
        scheduler_mode=SchedulerMode(
            os.getenv(SCHEDULER_MODE_ENV, definition.scheduler_mode.value)
        ),
        integrations=IntegrationModes(
            ae200=ae200_simulator_enabled(),
            hubitat=hubitat_simulator_enabled(),
            airthings=airthings_simulator_enabled(),
            aqicn=aqicn_simulator_enabled(),
        ),
    )
    if policy.control_mode is not definition.control_mode:
        raise ValueError(f"{CONTROL_MODE_ENV} does not match the instance policy")
    if policy.scheduler_mode is not definition.scheduler_mode:
        raise ValueError(f"{SCHEDULER_MODE_ENV} does not match the instance policy")
    if policy.database_identity != definition.database_identity:
        raise ValueError(f"{DATABASE_IDENTITY_ENV} does not match the instance policy")
    if policy.integrations != definition.integrations:
        raise ValueError("simulator environment does not match the instance policy")
    return policy


SIMULATOR_ENVIRONMENTS = (
    AE200_SIMULATOR_ENV,
    HUBITAT_SIMULATOR_ENV,
    AIRTHINGS_SIMULATOR_ENV,
    AQICN_SIMULATOR_ENV,
)
