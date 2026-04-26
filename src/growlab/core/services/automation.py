from __future__ import annotations

from datetime import timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from growlab.core.app.dependencies import get_actuator_state_service
from growlab.core.config.models import ActionConfig, ConditionConfig, ConditionGroupConfig
from growlab.core.config.registry import EntityRegistry
from growlab.core.db.repo_events import (
    get_latest_actuator_event,
    get_latest_automation_event,
    insert_automation_event,
)
from growlab.core.db.repo_readings import get_latest_sensor_metrics
from growlab.core.schemas.api import ActuatorCommandPayload
from growlab.core.services.commands import CommandService
from growlab.core.services.garden import (
    ActuatorRuntimeState,
    GardenController,
    GardenRuntimeState,
    ManualOverrideDirective,
)
from growlab.core.services.overrides import ManualOverrideService
from growlab.shared.time import utc_now


class AutomationService:
    def run_cycle(self, *, registry: EntityRegistry, session: Session) -> dict:
        results = []
        ManualOverrideService().cleanup_expired(session)
        for automation_id, automation in registry.config.automations.items():
            if not automation.enabled:
                continue

            if automation.mode == "garden_v1":
                result = self._run_garden_cycle(
                    registry=registry,
                    session=session,
                    automation_id=automation_id,
                )
                results.append(result)
                continue

            latest_event = get_latest_automation_event(session, automation_id=automation_id)
            on_match = self._evaluate_group(registry, session, automation.logic.on if automation.logic else None)
            off_match = self._evaluate_group(registry, session, automation.logic.off if automation.logic else None)

            decision = "noop"
            actions: list[ActionConfig] = []
            reason = "no_conditions_matched"

            if on_match:
                decision = "on"
                actions = automation.actions.on if automation.actions else []
                reason = "on_conditions_matched"
            elif off_match:
                decision = "off"
                actions = automation.actions.off if automation.actions else []
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

    def _run_garden_cycle(
        self,
        *,
        registry: EntityRegistry,
        session: Session,
        automation_id: str,
    ) -> dict:
        automation = registry.config.automations[automation_id]
        now_utc = utc_now()
        now_local = now_utc.astimezone(ZoneInfo(registry.config.app.timezone))
        runtime = self._build_garden_runtime(
            registry=registry,
            session=session,
            automation_id=automation_id,
        )
        manual_overrides = [
            ManualOverrideDirective(
                actuator_id=item.actuator_id,
                power=item.power,
                mode=item.mode,
                source=item.source,
                reason=item.reason,
            )
            for item in ManualOverrideService().active_commands(session)
        ]
        evaluation = GardenController().evaluate(
            automation_id=automation_id,
            automation=automation,
            runtime=runtime,
            now_utc=now_utc,
            now_local=now_local,
            manual_overrides=manual_overrides,
        )

        action_results: list[dict[str, Any]] = []
        skipped_actions: list[dict[str, Any]] = []
        for command in evaluation.commands:
            if self._command_matches_state(runtime, command.actuator_id, command.command):
                skipped_actions.append(
                    {
                        "actuator_id": command.actuator_id,
                        "command": command.command,
                        "reason": "already_at_target",
                        "source": command.source,
                    }
                )
                continue

            command_result = CommandService().issue_command(
                registry=registry,
                session=session,
                actuator_id=command.actuator_id,
                payload=ActuatorCommandPayload(command=command.command),
            )
            action_results.append(
                {
                    **command_result,
                    "reason": command.reason,
                    "source": command.source,
                }
            )

        event_payload = {
            "decision": evaluation.decision,
            "action_results": action_results,
            "skipped_actions": skipped_actions,
            "diagnostics": evaluation.diagnostics,
        }
        insert_automation_event(
            session,
            automation_id=automation_id,
            ts_utc=now_utc,
            decision=evaluation.decision,
            reason=evaluation.reason,
            payload=event_payload,
        )
        return {
            "automation_id": automation_id,
            "decision": evaluation.decision,
            "reason": evaluation.reason,
            "action_count": len(action_results),
            "skipped_count": len(skipped_actions),
        }

    def _build_garden_runtime(
        self,
        *,
        registry: EntityRegistry,
        session: Session,
        automation_id: str,
    ) -> GardenRuntimeState:
        automation = registry.config.automations[automation_id]
        runtime = GardenRuntimeState()
        controller = automation.controller
        if controller is None:
            return runtime

        sensor_refs: set[tuple[str, str]] = set()
        actuator_ids: set[str] = set()

        if controller.climate:
            for device in (controller.climate.fan, controller.climate.heat):
                if device is None:
                    continue
                actuator_ids.add(device.actuator)
                for band in device.bands:
                    sensor_refs.add((band.sensor, band.metric))

        if controller.light:
            actuator_ids.add(controller.light.actuator)

        if controller.watering:
            actuator_ids.add(controller.watering.actuator)
            if controller.watering.sensor:
                sensor_refs.add((controller.watering.sensor.sensor, controller.watering.sensor.metric))

        if controller.emergency:
            for condition in controller.emergency.when.all or []:
                sensor_refs.add((condition.sensor, condition.metric))
            for condition in controller.emergency.when.any or []:
                sensor_refs.add((condition.sensor, condition.metric))
            for action in controller.emergency.actions.on:
                actuator_ids.add(action.actuator)
            for action in controller.emergency.actions.off:
                actuator_ids.add(action.actuator)

        latest_by_sensor: dict[str, dict[str, Any]] = {}
        for sensor_id, metric in sensor_refs:
            latest = latest_by_sensor.setdefault(
                sensor_id,
                get_latest_sensor_metrics(session, sensor_id=sensor_id),
            )
            value = latest.get(metric)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                runtime.sensors[(sensor_id, metric)] = float(value)

        live_states = get_actuator_state_service().get_states(
            registry=registry,
            session=session,
        )
        for actuator_id in actuator_ids:
            latest_event = get_latest_actuator_event(session, actuator_id=actuator_id)
            power = live_states[actuator_id].power
            ts_utc = None
            if latest_event:
                ts_utc = latest_event.ts_utc.replace(tzinfo=timezone.utc)
            runtime.actuators[actuator_id] = ActuatorRuntimeState(
                power=power,
                last_changed_utc=ts_utc,
            )
        return runtime

    def _command_matches_state(
        self,
        runtime: GardenRuntimeState,
        actuator_id: str,
        command: dict[str, Any],
    ) -> bool:
        power = command.get("power")
        if not isinstance(power, bool):
            return False
        return runtime.actuator_state(actuator_id).power is power

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
