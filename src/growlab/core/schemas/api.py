from __future__ import annotations

from datetime import datetime
from typing import Any, Union

from pydantic import BaseModel, Field


class SensorIngestPayload(BaseModel):
    ts_utc: datetime
    metrics: dict[str, Union[float, int, str, bool, None]] = Field(default_factory=dict)


class CollectorHeartbeatPayload(BaseModel):
    ts_utc: datetime
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ActuatorCommandPayload(BaseModel):
    command: dict[str, Any] = Field(default_factory=dict)
