from __future__ import annotations

from datetime import timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from growlab.core.config.models import ActionConfig, ConditionConfig, ConditionGroupConfig
from growlab.core.config.registry import EntityRegistry
from growlab.core.db.repo_events import get_latest_automation_event, insert_automation_event
from growlab.core.db.repo_readings import get_latest_sensor_metrics
from growlab.core.schemas.api import ActuatorCommandPayload
from growlab.core.services.commands import CommandService
from growlab.shared.time import utc_now


class AutomationService:
    def run_cycle(self, *, registry: EntityRegistry, session: Session) -> dict:
        results = []
        for automation_id, automation in registry.config.automations.items():
            if not automation.enabled:
                continue

            latest_event = get_latest_automation_event(session, automation_id=automation_id)
            on_match = self._evaluate_group(registry, session, automation.logic.on)
            off_match = self._evaluate_group(registry, session, automation.logic.off)

            decision = "noop"
            actions: list[ActionConfig] = []
            reason = "no_conditions_matched"

            if on_match:
                decision = "on"
                actions = automation.actions.on
                reason = "on_conditions_matched"
            elif off_match:
                decision = "off"
                actions = automation.actions.off
                reason = "off_conditions_matched"

            if (
                latest_event
                and latest_event.decision in {"on", "off"}
                and automation.cooldown_seconds
                and (
                    utc_now()
                    - latest_event.ts_utc.replace(tzinfo=timezone.utc)
                ).total_seconds()
                < automation.cooldown_seconds
            ):
                decision = "cooldown"
                actions = []
                reason = "cooldown_active"

            action_results: list[dict[str, Any]] = []
            for action in actions:
                command_result = CommandService().issue_command(
                    registry=registry,
                    session=session,
                    actuator_id=action.actuator,
                    payload=ActuatorCommandPayload(command=action.command),
                )
                action_results.append(command_result)

            event_payload = {"decision": decision, "action_results": action_results}
            insert_automation_event(
                session,
                automation_id=automation_id,
                ts_utc=utc_now(),
                decision=decision,
                reason=reason,
                payload=event_payload,
            )
            results.append(
                {
                    "automation_id": automation_id,
                    "decision": decision,
                    "reason": reason,
                    "action_count": len(action_results),
                }
            )
        return {"status": "ok", "results": results}

    def _evaluate_group(
        self,
        registry: EntityRegistry,
        session: Session,
        group: Optional[ConditionGroupConfig],
    ) -> bool:
        if group is None:
            return False
        if group.all:
            return all(self._evaluate_condition(registry, session, condition) for condition in group.all)
        if group.any:
            return any(self._evaluate_condition(registry, session, condition) for condition in group.any)
        return False

    def _evaluate_condition(
        self,
        registry: EntityRegistry,
        session: Session,
        condition: ConditionConfig,
    ) -> bool:
        registry.get_sensor(condition.sensor)
        latest = get_latest_sensor_metrics(session, sensor_id=condition.sensor)
        current_value = latest.get(condition.metric)
        if current_value is None or isinstance(current_value, str):
            return False

        if condition.op == ">":
            return current_value > condition.value
        if condition.op == ">=":
            return current_value >= condition.value
        if condition.op == "<":
            return current_value < condition.value
        if condition.op == "<=":
            return current_value <= condition.value
        if condition.op == "=":
            return abs(current_value - condition.value) < 0.0001
        return False
