from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    name: str
    timezone: str
    database_url: str
    ingest_base_url: str
    automation_interval_seconds: int = Field(default=30, gt=0)


class CollectorConfig(BaseModel):
    label: str
    enabled: bool = True


class MetricConfig(BaseModel):
    label: str
    unit: Optional[str] = None


class PollConfig(BaseModel):
    every_seconds: int = Field(gt=0)


class CollectorSourceConfig(BaseModel):
    kind: Literal["collector"]
    collector_id: str
    driver: str
    poll: PollConfig
    config: dict[str, Any] = Field(default_factory=dict)


class RemoteSourceConfig(BaseModel):
    kind: Literal["remote"]
    protocol: Literal["http_push"]
    auth_token: str


class SensorConfig(BaseModel):
    label: str
    enabled: bool = True
    source: Union[CollectorSourceConfig, RemoteSourceConfig]
    metrics: dict[str, MetricConfig]


class CommandFieldConfig(BaseModel):
    type: str


class ActuatorConfig(BaseModel):
    label: str
    driver: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    commands: dict[str, CommandFieldConfig] = Field(default_factory=dict)


class ConditionConfig(BaseModel):
    sensor: str
    metric: str
    op: str
    value: float
    for_seconds: Optional[int] = None


class ConditionGroupConfig(BaseModel):
    all: Optional[list[ConditionConfig]] = None
    any: Optional[list[ConditionConfig]] = None


class ActionConfig(BaseModel):
    actuator: str
    command: dict[str, Any]


class AutomationLogicConfig(BaseModel):
    on: Optional[ConditionGroupConfig] = None
    off: Optional[ConditionGroupConfig] = None


class AutomationActionsConfig(BaseModel):
    on: list[ActionConfig] = Field(default_factory=list)
    off: list[ActionConfig] = Field(default_factory=list)


class AutomationConfig(BaseModel):
    enabled: bool = True
    mode: str = "stateful"
    logic: AutomationLogicConfig
    actions: AutomationActionsConfig
    cooldown_seconds: Optional[int] = None


class DashboardPanelConfig(BaseModel):
    panel: str
    entity: str


class DashboardConfig(BaseModel):
    title: str
    layout: list[DashboardPanelConfig] = Field(default_factory=list)


class DriverRegistryConfig(BaseModel):
    collector_sensor: dict[str, str] = Field(default_factory=dict)
    actuator: dict[str, str] = Field(default_factory=dict)


class GrowLabConfig(BaseModel):
    app: AppConfig
    collectors: dict[str, CollectorConfig] = Field(default_factory=dict)
    drivers: DriverRegistryConfig
    sensors: dict[str, SensorConfig] = Field(default_factory=dict)
    actuators: dict[str, ActuatorConfig] = Field(default_factory=dict)
    automations: dict[str, AutomationConfig] = Field(default_factory=dict)
    dashboards: dict[str, DashboardConfig] = Field(default_factory=dict)
