from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class SensorIngestPayload(BaseModel):
    ts_utc: datetime
    metrics: dict[str, Union[float, int, str, bool, None]] = Field(default_factory=dict)


class CollectorHeartbeatPayload(BaseModel):
    ts_utc: datetime
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ActuatorCommandPayload(BaseModel):
    command: dict[str, Any] = Field(default_factory=dict)


class ManualOverridePayload(BaseModel):
    mode: Literal["on", "off", "pulse"]
    expires_after_minutes: Optional[int] = Field(default=None, gt=0)
    pulse_seconds: Optional[int] = Field(default=None, gt=0)
    reason: Optional[str] = None
    source: str = "dashboard"


class ClimateConfigPatchPayload(BaseModel):
    mode: Literal["simple", "advanced"] = "simple"
    temperature_on_above: Optional[float] = None
    temperature_off_below: Optional[float] = None
    humidity_on_above: Optional[float] = None
    humidity_off_below: Optional[float] = None
    heat_on_below: Optional[float] = None
    heat_off_above: Optional[float] = None
    temp_sensor: str = "air_lab"
    humidity_sensor: str = "air_lab"
    fan_actuator: str = "exhaust_fan"
    heat_actuator: str = "warm_pads"
    advanced: Optional[dict[str, Any]] = None


class LightingConfigPatchPayload(BaseModel):
    mode: Literal["simple", "advanced"] = "simple"
    actuator: str = "lamps"
    start: Optional[str] = None
    end: Optional[str] = None
    advanced: Optional[dict[str, Any]] = None


class WateringConfigPatchPayload(BaseModel):
    mode: Literal["simple", "advanced"] = "simple"
    actuator: str = "water_pump"
    watering_mode: Optional[Literal["schedule", "sensor"]] = None
    interval_minutes: Optional[int] = Field(default=None, gt=0)
    run_seconds: Optional[int] = Field(default=None, gt=0)
    anchor: Optional[str] = None
    sensor: str = "soil_tray_1"
    metric: str = "moisture_pct"
    start_below: Optional[float] = None
    stop_above: Optional[float] = None
    max_run_seconds: Optional[int] = Field(default=None, gt=0)
    advanced: Optional[dict[str, Any]] = None

    @field_validator(
        "interval_minutes",
        "run_seconds",
        "anchor",
        "start_below",
        "stop_above",
        "max_run_seconds",
        mode="before",
    )
    @classmethod
    def blank_optional_values_are_absent(cls, value):
        return None if value == "" else value


class EmergencyConfigPatchPayload(BaseModel):
    mode: Literal["simple", "advanced"] = "simple"
    high_temp: Optional[float] = None
    high_humidity: Optional[float] = None
    temp_sensor: str = "air_lab"
    humidity_sensor: str = "air_lab"
    fan_actuator: str = "exhaust_fan"
    lamps_actuator: str = "lamps"
    pads_actuator: str = "warm_pads"
    pump_actuator: str = "water_pump"
    fan_on: bool = True
    lamps_off: bool = True
    pads_off: bool = True
    pump_off: bool = False
    advanced: Optional[dict[str, Any]] = None


class GardenModuleEnabledPayload(BaseModel):
    enabled: bool
