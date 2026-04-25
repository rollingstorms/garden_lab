from __future__ import annotations

from datetime import timezone
from typing import Any

from sqlalchemy.orm import Session

from growlab.core.config.registry import EntityRegistry
from growlab.core.db.repo_events import (
    get_latest_actuator_event,
    get_latest_automation_event,
    list_recent_actuator_events,
    list_recent_automation_events,
    list_recent_system_events,
)
from growlab.core.db.repo_overrides import get_active_manual_override
from growlab.core.db.repo_readings import get_latest_sensor_metrics, get_sensor_history
from growlab.core.services.configuration import ConfigService, GARDEN_AUTOMATION_ID
from growlab.core.services.overrides import ManualOverrideService


class GardenStateService:
    def snapshot(
        self,
        *,
        registry: EntityRegistry,
        session: Session,
    ) -> dict[str, Any]:
        override_service = ManualOverrideService()
        override_service.cleanup_expired(session)
        latest_decision = get_latest_automation_event(session, automation_id=GARDEN_AUTOMATION_ID)
        garden_config = ConfigService().get_garden_config()
        sensors = self._build_sensor_state(registry=registry, session=session)
        actuators = self._build_actuator_state(registry=registry, session=session)
        return {
            "generated_at": (latest_decision.ts_utc.isoformat() if latest_decision else None),
            "automation_id": GARDEN_AUTOMATION_ID,
            "timezone": registry.config.app.timezone,
            "decision": {
                "reason": latest_decision.reason if latest_decision else None,
                "decision": latest_decision.decision if latest_decision else None,
                "ts_utc": latest_decision.ts_utc.isoformat() if latest_decision else None,
                "diagnostics": latest_decision.payload_json.get("diagnostics", {}) if latest_decision else {},
            },
            "emergency": {
                "active": bool(
                    latest_decision and latest_decision.reason == "garden_emergency"
                ),
                "message": (
                    "Emergency override active"
                    if latest_decision and latest_decision.reason == "garden_emergency"
                    else None
                ),
            },
            "sensors": sensors,
            "actuators": actuators,
            "config": garden_config,
            "history": self._build_history(session=session),
        }

    def _build_sensor_state(self, *, registry: EntityRegistry, session: Session) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for sensor_id, sensor in registry.config.sensors.items():
            latest = get_latest_sensor_metrics(session, sensor_id=sensor_id)
            history = {}
            for metric_id in sensor.metrics:
                history[metric_id] = [
                    {
                        "ts_utc": row.ts_utc.isoformat(),
                        "value": row.value_num if row.value_num is not None else row.value_text,
                    }
                    for row in get_sensor_history(session, sensor_id=sensor_id, metric=metric_id, limit=48)
                ]
            data[sensor_id] = {
                "label": sensor.label,
                "metrics": {
                    metric_id: {
                        "label": metric.label,
                        "unit": metric.unit,
                        "value": latest.get(metric_id),
                    }
                    for metric_id, metric in sensor.metrics.items()
                },
                "history": history,
            }
        return data

    def _build_actuator_state(self, *, registry: EntityRegistry, session: Session) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for actuator_id, actuator in registry.config.actuators.items():
            latest_event = get_latest_actuator_event(session, actuator_id=actuator_id)
            active_override = get_active_manual_override(session, actuator_id=actuator_id)
            power = None
            if latest_event and isinstance(latest_event.payload_json.get("command"), dict):
                power = latest_event.payload_json["command"].get("power")
            badge = "auto"
            if active_override:
                badge = "pulse" if active_override.mode == "pulse" else "manual"
            latest_decision_reason = None
            decision_event = get_latest_automation_event(session, automation_id=GARDEN_AUTOMATION_ID)
            if decision_event and decision_event.payload_json.get("action_results"):
                for result in reversed(decision_event.payload_json["action_results"]):
                    if result.get("actuator_id") == actuator_id:
                        latest_decision_reason = result.get("reason")
                        break
            if decision_event and decision_event.reason == "garden_emergency":
                emergency_off = {"warm_pads", "lamps", "water_pump"}
                if actuator_id == "exhaust_fan" or (actuator_id in emergency_off and power is False):
                    badge = "emergency"
            data[actuator_id] = {
                "label": actuator.label,
                "driver": actuator.driver,
                "power": power,
                "badge": badge,
                "last_command_at": latest_event.ts_utc.isoformat() if latest_event else None,
                "last_reason": latest_decision_reason,
                "override": (
                    {
                        "id": active_override.id,
                        "mode": active_override.mode,
                        "reason": active_override.reason,
                        "expires_at_utc": active_override.expires_at_utc.replace(tzinfo=timezone.utc).isoformat()
                        if active_override.expires_at_utc.tzinfo is None
                        else active_override.expires_at_utc.isoformat(),
                        "pulse_seconds": active_override.pulse_seconds,
                    }
                    if active_override
                    else None
                ),
            }
        return data

    def _build_history(self, *, session: Session) -> dict[str, Any]:
        decision_history = [
            {
                "ts_utc": row.ts_utc.isoformat(),
                "decision": row.decision,
                "reason": row.reason,
                "payload": row.payload_json,
            }
            for row in list_recent_automation_events(session, automation_id=GARDEN_AUTOMATION_ID, limit=30)
        ]
        actuator_events = [
            {
                "ts_utc": row.ts_utc.isoformat(),
                "actuator_id": row.actuator_id,
                "event_type": row.event_type,
                "status": row.status,
                "payload": row.payload_json,
            }
            for row in list_recent_actuator_events(session, limit=100)
        ]
        return {
            "decision_history": decision_history,
            "manual_overrides": [
                {
                    "id": row.id,
                    "actuator_id": row.actuator_id,
                    "mode": row.mode,
                    "status": row.status,
                    "reason": row.reason,
                    "pulse_seconds": row.pulse_seconds,
                    "created_at_utc": row.created_at_utc.isoformat(),
                    "expires_at_utc": row.expires_at_utc.isoformat(),
                }
                for row in ManualOverrideService().recent_history(session, limit=30)
            ],
            "actuator_events": actuator_events,
            "emergency_events": [
                item
                for item in decision_history
                if item["reason"] == "garden_emergency"
            ],
            "config_events": [
                {
                    "ts_utc": row.ts_utc.isoformat(),
                    "event_type": row.event_type,
                    "message": row.message,
                    "payload": row.payload_json,
                }
                for row in list_recent_system_events(session, category="config", limit=20)
            ],
        }
