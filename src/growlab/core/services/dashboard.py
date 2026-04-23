from __future__ import annotations

from sqlalchemy.orm import Session

from growlab.core.config.registry import EntityRegistry
from growlab.core.db.repo_events import get_latest_actuator_event, get_latest_automation_event
from growlab.core.db.repo_readings import get_latest_sensor_metrics, get_sensor_history


class DashboardService:
    def build_dashboard_view(
        self,
        *,
        registry: EntityRegistry,
        session: Session,
        dashboard_id: str = "main",
    ) -> dict:
        dashboard = registry.config.dashboards[dashboard_id]
        panels: list[dict] = []

        for item in dashboard.layout:
            entity_id = item.entity
            if entity_id in registry.config.sensors:
                sensor = registry.get_sensor(entity_id)
                metrics = list(sensor.metrics.keys())
                history = {
                    metric: [
                        {
                            "ts_utc": row.ts_utc.isoformat(),
                            "value_num": row.value_num,
                            "value_text": row.value_text,
                        }
                        for row in get_sensor_history(session, sensor_id=entity_id, metric=metric, limit=10)
                    ]
                    for metric in metrics
                }
                panels.append(
                    {
                        "panel": item.panel,
                        "entity_type": "sensor",
                        "entity_id": entity_id,
                        "label": sensor.label,
                        "metrics": sensor.metrics,
                        "latest": get_latest_sensor_metrics(session, sensor_id=entity_id),
                        "history": history,
                    }
                )
            elif entity_id in registry.config.actuators:
                actuator = registry.get_actuator(entity_id)
                latest_event = get_latest_actuator_event(session, actuator_id=entity_id)
                panels.append(
                    {
                        "panel": item.panel,
                        "entity_type": "actuator",
                        "entity_id": entity_id,
                        "label": actuator.label,
                        "driver": actuator.driver,
                        "latest_event": latest_event,
                    }
                )
            elif entity_id in registry.config.automations:
                automation = registry.config.automations[entity_id]
                latest_event = get_latest_automation_event(session, automation_id=entity_id)
                panels.append(
                    {
                        "panel": item.panel,
                        "entity_type": "automation",
                        "entity_id": entity_id,
                        "label": entity_id,
                        "enabled": automation.enabled,
                        "mode": automation.mode,
                        "latest_event": latest_event,
                    }
                )
            else:
                panels.append(
                    {
                        "panel": item.panel,
                        "entity_type": "unknown",
                        "entity_id": entity_id,
                        "label": entity_id,
                    }
                )

        return {"title": dashboard.title, "panels": panels}
