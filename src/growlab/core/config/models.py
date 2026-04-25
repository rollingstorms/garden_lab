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


class EnvironmentBandConfig(BaseModel):
    sensor: str
    metric: str
    on_above: Optional[float] = None
    off_below: Optional[float] = None
    on_below: Optional[float] = None
    off_above: Optional[float] = None


class ClimateDeviceConfig(BaseModel):
    actuator: str
    bands: list[EnvironmentBandConfig] = Field(default_factory=list)


class ClimateControlConfig(BaseModel):
    enabled: bool = True
    fan: Optional[ClimateDeviceConfig] = None
    heat: Optional[ClimateDeviceConfig] = None


class TimeRangeConfig(BaseModel):
    start: str
    end: str


class LightControlConfig(BaseModel):
    enabled: bool = True
    actuator: str
    schedule: TimeRangeConfig


class TimedWateringConfig(BaseModel):
    interval_minutes: int = Field(gt=0)
    run_seconds: int = Field(gt=0)
    anchor: str = "00:00"


class SensorWateringConfig(BaseModel):
    sensor: str
    metric: str
    start_below: float
    stop_above: Optional[float] = None
    max_run_seconds: Optional[int] = Field(default=None, gt=0)


class WateringControlConfig(BaseModel):
    enabled: bool = True
    actuator: str
    mode: Literal["schedule", "sensor"]
    schedule: Optional[TimedWateringConfig] = None
    sensor: Optional[SensorWateringConfig] = None


class EmergencyActionsConfig(BaseModel):
    on: list[ActionConfig] = Field(default_factory=list)
    off: list[ActionConfig] = Field(default_factory=list)


class EmergencyControlConfig(BaseModel):
    enabled: bool = True
    when: ConditionGroupConfig
    actions: EmergencyActionsConfig


class GardenControllerConfig(BaseModel):
    climate: Optional[ClimateControlConfig] = None
    light: Optional[LightControlConfig] = None
    watering: Optional[WateringControlConfig] = None
    emergency: Optional[EmergencyControlConfig] = None


class AutomationConfig(BaseModel):
    enabled: bool = True
    mode: str = "stateful"
    logic: Optional[AutomationLogicConfig] = None
    actions: Optional[AutomationActionsConfig] = None
    controller: Optional[GardenControllerConfig] = None
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
