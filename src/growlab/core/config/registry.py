from __future__ import annotations

from dataclasses import dataclass

from growlab.core.config.models import ActuatorConfig, GrowLabConfig, SensorConfig


@dataclass
class EntityRegistry:
    config: GrowLabConfig

    def get_sensor(self, sensor_id: str) -> SensorConfig:
        return self.config.sensors[sensor_id]

    def get_actuator(self, actuator_id: str) -> ActuatorConfig:
        return self.config.actuators[actuator_id]

    def dashboard_ids(self) -> list[str]:
        return list(self.config.dashboards.keys())
