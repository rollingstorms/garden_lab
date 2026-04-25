from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Optional

from growlab.core.config.models import (
    ActionConfig,
    AutomationConfig,
    ClimateDeviceConfig,
    EnvironmentBandConfig,
)


@dataclass
class ActuatorRuntimeState:
    power: Optional[bool] = None
    last_changed_utc: Optional[datetime] = None


@dataclass
class GardenRuntimeState:
    sensors: dict[tuple[str, str], float] = field(default_factory=dict)
    actuators: dict[str, ActuatorRuntimeState] = field(default_factory=dict)

    def sensor_value(self, sensor_id: str, metric: str) -> Optional[float]:
        return self.sensors.get((sensor_id, metric))

    def actuator_state(self, actuator_id: str) -> ActuatorRuntimeState:
        return self.actuators.get(actuator_id, ActuatorRuntimeState())


@dataclass
class ManualOverrideDirective:
    actuator_id: str
    power: bool
    mode: str
    source: str = "manual_override"
    reason: str = "manual_override_active"
    priority: int = 60


@dataclass
class ProposedCommand:
    actuator_id: str
    command: dict[str, object]
    reason: str
    source: str
    priority: int = 10


@dataclass
class GardenEvaluation:
    decision: str
    reason: str
    commands: list[ProposedCommand]
    diagnostics: dict[str, object]


class GardenController:
    def evaluate(
        self,
        *,
        automation_id: str,
        automation: AutomationConfig,
        runtime: GardenRuntimeState,
        now_utc: datetime,
        now_local: datetime,
        manual_overrides: Optional[list[ManualOverrideDirective]] = None,
    ) -> GardenEvaluation:
        controller = automation.controller
        if controller is None:
            raise ValueError(f"Automation {automation_id} is missing controller config")

        proposals: dict[str, ProposedCommand] = {}
        diagnostics: dict[str, object] = {"modules": {}}

        emergency_active = False
        if controller.emergency:
            emergency_active = _evaluate_condition_group(
                controller.emergency.when,
                runtime=runtime,
            )
            diagnostics["modules"]["emergency"] = {"active": emergency_active}
            if emergency_active:
                self._merge_actions(
                    proposals,
                    controller.emergency.actions.on,
                    reason="emergency_force_on",
                    source="emergency",
                    priority=100,
                )
                self._merge_actions(
                    proposals,
                    controller.emergency.actions.off,
                    reason="emergency_force_off",
                    source="emergency",
                    priority=100,
                )

        if controller.climate:
            climate_commands, climate_diag = self._evaluate_climate(
                climate=controller.climate,
                runtime=runtime,
            )
            diagnostics["modules"]["climate"] = climate_diag
            for command in climate_commands:
                self._merge_command(proposals, command)

        if controller.light:
            lights_on = _time_in_range(
                now_local.time(),
                start=_parse_clock(controller.light.schedule.start),
                end=_parse_clock(controller.light.schedule.end),
            )
            diagnostics["modules"]["light"] = {
                "lights_on": lights_on,
                "local_time": now_local.isoformat(),
            }
            self._merge_command(
                proposals,
                ProposedCommand(
                    actuator_id=controller.light.actuator,
                    command={"power": lights_on},
                    reason="light_schedule_active" if lights_on else "light_schedule_inactive",
                    source="light",
                    priority=20,
                ),
            )

        if controller.watering:
            watering_command, watering_diag = self._evaluate_watering(
                automation=automation,
                runtime=runtime,
                now_utc=now_utc,
                now_local=now_local,
            )
            diagnostics["modules"]["watering"] = watering_diag
            if watering_command:
                self._merge_command(proposals, watering_command)

        diagnostics["modules"]["manual_overrides"] = []
        for override in manual_overrides or []:
            diagnostics["modules"]["manual_overrides"].append(
                {
                    "actuator_id": override.actuator_id,
                    "mode": override.mode,
                    "power": override.power,
                }
            )
            self._merge_command(
                proposals,
                ProposedCommand(
                    actuator_id=override.actuator_id,
                    command={"power": override.power},
                    reason=override.reason,
                    source=override.source,
                    priority=override.priority,
                ),
            )

        ordered_commands = sorted(proposals.values(), key=lambda item: (-item.priority, item.actuator_id))
        reason = "garden_emergency" if emergency_active else "garden_balancing"
        return GardenEvaluation(
            decision="control",
            reason=reason,
            commands=ordered_commands,
            diagnostics=diagnostics,
        )

    def _evaluate_climate(
        self,
        *,
        climate,
        runtime: GardenRuntimeState,
    ) -> tuple[list[ProposedCommand], dict[str, object]]:
        commands: list[ProposedCommand] = []
        diagnostics: dict[str, object] = {}

        for source, device in (("fan", climate.fan), ("heat", climate.heat)):
            if device is None:
                continue
            power, device_diag = evaluate_device_bands(device=device, runtime=runtime)
            diagnostics[source] = device_diag
            if power is None:
                continue
            commands.append(
                ProposedCommand(
                    actuator_id=device.actuator,
                    command={"power": power},
                    reason=f"{source}_climate_on" if power else f"{source}_climate_off",
                    source="climate",
                    priority=30,
                )
            )
        return commands, diagnostics

    def _evaluate_watering(
        self,
        *,
        automation: AutomationConfig,
        runtime: GardenRuntimeState,
        now_utc: datetime,
        now_local: datetime,
    ) -> tuple[Optional[ProposedCommand], dict[str, object]]:
        controller = automation.controller
        if controller is None or controller.watering is None:
            return None, {}

        watering = controller.watering
        actuator_state = runtime.actuator_state(watering.actuator)

        if watering.mode == "schedule":
            if watering.schedule is None:
                raise ValueError("Schedule watering mode requires schedule config")
            anchor = _parse_clock(watering.schedule.anchor)
            active = _scheduled_window_active(
                now_local=now_local,
                anchor=anchor,
                interval_minutes=watering.schedule.interval_minutes,
                run_seconds=watering.schedule.run_seconds,
            )
            return (
                ProposedCommand(
                    actuator_id=watering.actuator,
                    command={"power": active},
                    reason="watering_schedule_active" if active else "watering_schedule_inactive",
                    source="watering",
                    priority=20,
                ),
                {"mode": "schedule", "active": active},
            )

        if watering.sensor is None:
            raise ValueError("Sensor watering mode requires sensor config")

        moisture = runtime.sensor_value(watering.sensor.sensor, watering.sensor.metric)
        if moisture is None:
            return None, {"mode": "sensor", "status": "missing_sensor_value"}

        stop_above = watering.sensor.stop_above
        if stop_above is None:
            stop_above = watering.sensor.start_below

        power = actuator_state.power
        if moisture <= watering.sensor.start_below:
            power = True
        elif moisture >= stop_above:
            power = False
        elif power is None:
            power = False

        max_run_hit = False
        if (
            power
            and watering.sensor.max_run_seconds
            and actuator_state.last_changed_utc is not None
            and (now_utc - actuator_state.last_changed_utc) >= timedelta(seconds=watering.sensor.max_run_seconds)
        ):
            power = False
            max_run_hit = True

        return (
            ProposedCommand(
                actuator_id=watering.actuator,
                command={"power": power},
                reason="watering_sensor_dry" if power else "watering_sensor_satisfied",
                source="watering",
                priority=20,
            ),
            {
                "mode": "sensor",
                "moisture": moisture,
                "max_run_hit": max_run_hit,
            },
        )

    def _merge_actions(
        self,
        proposals: dict[str, ProposedCommand],
        actions: list[ActionConfig],
        *,
        reason: str,
        source: str,
        priority: int,
    ) -> None:
        for action in actions:
            self._merge_command(
                proposals,
                ProposedCommand(
                    actuator_id=action.actuator,
                    command=action.command,
                    reason=reason,
                    source=source,
                    priority=priority,
                ),
            )

    def _merge_command(
        self,
        proposals: dict[str, ProposedCommand],
        command: ProposedCommand,
    ) -> None:
        existing = proposals.get(command.actuator_id)
        if existing is None or command.priority >= existing.priority:
            proposals[command.actuator_id] = command


def _evaluate_condition_group(group, *, runtime: GardenRuntimeState) -> bool:
    if group.all:
        return all(_evaluate_condition(condition, runtime=runtime) for condition in group.all)
    if group.any:
        return any(_evaluate_condition(condition, runtime=runtime) for condition in group.any)
    return False


def _evaluate_condition(condition, *, runtime: GardenRuntimeState) -> bool:
    current_value = runtime.sensor_value(condition.sensor, condition.metric)
    if current_value is None:
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


def _parse_clock(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(hour=int(hour), minute=int(minute))


def _time_in_range(current: time, *, start: time, end: time) -> bool:
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def _scheduled_window_active(
    *,
    now_local: datetime,
    anchor: time,
    interval_minutes: int,
    run_seconds: int,
) -> bool:
    anchor_dt = now_local.replace(
        hour=anchor.hour,
        minute=anchor.minute,
        second=0,
        microsecond=0,
    )
    if now_local < anchor_dt:
        anchor_dt -= timedelta(days=1)
    elapsed = (now_local - anchor_dt).total_seconds()
    interval_seconds = interval_minutes * 60
    return elapsed % interval_seconds < run_seconds


def evaluate_band(
    *,
    band: EnvironmentBandConfig,
    current_value: Optional[float],
    current_power: Optional[bool],
) -> Optional[bool]:
    if current_value is None:
        return None
    if band.on_above is not None and current_value >= band.on_above:
        return True
    if band.off_below is not None and current_value <= band.off_below:
        return False
    if band.on_below is not None and current_value <= band.on_below:
        return True
    if band.off_above is not None and current_value >= band.off_above:
        return False
    return current_power


def evaluate_device_bands(
    *,
    device: ClimateDeviceConfig,
    runtime: GardenRuntimeState,
) -> tuple[Optional[bool], dict[str, object]]:
    actuator_state = runtime.actuator_state(device.actuator)
    decisions: list[Optional[bool]] = []
    details: list[dict[str, object]] = []
    for band in device.bands:
        value = runtime.sensor_value(band.sensor, band.metric)
        result = evaluate_band(
            band=band,
            current_value=value,
            current_power=actuator_state.power,
        )
        decisions.append(result)
        details.append(
            {
                "sensor": band.sensor,
                "metric": band.metric,
                "value": value,
                "decision": result,
            }
        )

    wanted_on = any(decision is True for decision in decisions)
    wanted_off = bool(decisions) and all(decision is False for decision in decisions if decision is not None)
    if wanted_on:
        return True, {"bands": details}
    if wanted_off and any(decision is not None for decision in decisions):
        return False, {"bands": details}
    return actuator_state.power, {"bands": details}
