from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from growlab.core.app.dependencies import get_config_paths, reset_runtime_caches
from growlab.core.config.loader import load_yaml_file
from growlab.core.config.models import (
    ClimateControlConfig,
    EmergencyControlConfig,
    GrowLabConfig,
    LightControlConfig,
    WateringControlConfig,
)
from growlab.core.db.repo_events import insert_system_event

GARDEN_AUTOMATION_ID = "garden_equilibrium"


class ConfigService:
    def get_garden_config(self) -> dict[str, Any]:
        base_path, local_path = get_config_paths()
        base_data = load_yaml_file(base_path)
        local_data = load_yaml_file(local_path)
        merged = _deep_merge(base_data, local_data)
        effective = GrowLabConfig.model_validate(merged)
        controller = effective.automations[GARDEN_AUTOMATION_ID].controller
        if controller is None:
            raise ValueError("Garden controller config is missing")
        base_controller = (
            base_data.get("automations", {})
            .get(GARDEN_AUTOMATION_ID, {})
            .get("controller", {})
        )
        local_controller = (
            local_data.get("automations", {})
            .get(GARDEN_AUTOMATION_ID, {})
            .get("controller", {})
        )
        return {
            "automation_id": GARDEN_AUTOMATION_ID,
            "effective": controller.model_dump(mode="json"),
            "base": base_controller,
            "override": local_controller,
            "diff": _diff_dict(base_controller, controller.model_dump(mode="json")),
        }

    def update_garden_module(
        self,
        *,
        module: str,
        payload: dict[str, Any],
        session,
    ) -> dict[str, Any]:
        base_path, local_path = get_config_paths()
        base_data = load_yaml_file(base_path)
        local_data = load_yaml_file(local_path)
        before_effective = self.get_garden_config()["effective"]

        local_mut = deepcopy(local_data)
        controller = (
            local_mut.setdefault("automations", {})
            .setdefault(GARDEN_AUTOMATION_ID, {})
            .setdefault("controller", {})
        )
        controller[module] = payload

        merged = _deep_merge(base_data, local_mut)
        validated = GrowLabConfig.model_validate(merged)
        effective_controller = validated.automations[GARDEN_AUTOMATION_ID].controller
        if effective_controller is None:
            raise ValueError("Updated garden controller config is missing")

        _write_yaml(local_path, local_mut)
        reset_runtime_caches()

        after_effective = effective_controller.model_dump(mode="json")
        insert_system_event(
            session,
            category="config",
            entity_id=module,
            event_type="config_updated",
            message=f"Updated garden {module} settings",
            payload={
                "module": module,
                "before": before_effective.get(module),
                "after": after_effective.get(module),
            },
        )
        return {
            "module": module,
            "effective": after_effective.get(module),
            "override": controller[module],
            "diff": _diff_dict(before_effective.get(module) or {}, after_effective.get(module) or {}),
        }

    def update_garden_module_enabled(
        self,
        *,
        module: str,
        enabled: bool,
        session,
    ) -> dict[str, Any]:
        base_path, local_path = get_config_paths()
        base_data = load_yaml_file(base_path)
        local_data = load_yaml_file(local_path)
        before_effective = self.get_garden_config()["effective"]

        local_mut = deepcopy(local_data)
        controller = (
            local_mut.setdefault("automations", {})
            .setdefault(GARDEN_AUTOMATION_ID, {})
            .setdefault("controller", {})
        )
        module_override = controller.setdefault(module, {})
        module_override["enabled"] = enabled

        merged = _deep_merge(base_data, local_mut)
        validated = GrowLabConfig.model_validate(merged)
        effective_controller = validated.automations[GARDEN_AUTOMATION_ID].controller
        if effective_controller is None:
            raise ValueError("Updated garden controller config is missing")

        _write_yaml(local_path, local_mut)
        reset_runtime_caches()

        after_effective = effective_controller.model_dump(mode="json")
        insert_system_event(
            session,
            category="config",
            entity_id=module,
            event_type="config_enabled_updated",
            message=f"Set garden {module} enabled={enabled}",
            payload={
                "module": module,
                "before": before_effective.get(module),
                "after": after_effective.get(module),
                "enabled": enabled,
            },
        )
        return {
            "module": module,
            "enabled": enabled,
            "effective": after_effective.get(module),
            "override": controller[module],
            "diff": _diff_dict(before_effective.get(module) or {}, after_effective.get(module) or {}),
        }


class GardenSettingsTranslator:
    def climate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("mode") == "advanced":
            return ClimateControlConfig.model_validate(payload["advanced"]).model_dump(mode="json")
        _require_keys(
            payload,
            [
                "temperature_on_above",
                "temperature_off_below",
                "humidity_on_above",
                "humidity_off_below",
                "heat_on_below",
                "heat_off_above",
            ],
        )
        if payload["temperature_on_above"] <= payload["temperature_off_below"]:
            raise ValueError("temperature_on_above must be greater than temperature_off_below")
        if payload["humidity_on_above"] <= payload["humidity_off_below"]:
            raise ValueError("humidity_on_above must be greater than humidity_off_below")
        if payload["heat_off_above"] <= payload["heat_on_below"]:
            raise ValueError("heat_off_above must be greater than heat_on_below")

        translated = {
            "fan": {
                "actuator": payload.get("fan_actuator", "exhaust_fan"),
                "bands": [
                    {
                        "sensor": payload.get("temp_sensor", "air_lab"),
                        "metric": "temperature_c",
                        "on_above": payload["temperature_on_above"],
                        "off_below": payload["temperature_off_below"],
                    },
                    {
                        "sensor": payload.get("humidity_sensor", "air_lab"),
                        "metric": "humidity_pct",
                        "on_above": payload["humidity_on_above"],
                        "off_below": payload["humidity_off_below"],
                    },
                ],
            },
            "heat": {
                "actuator": payload.get("heat_actuator", "warm_pads"),
                "bands": [
                    {
                        "sensor": payload.get("temp_sensor", "air_lab"),
                        "metric": "temperature_c",
                        "on_below": payload["heat_on_below"],
                        "off_above": payload["heat_off_above"],
                    }
                ],
            },
        }
        return ClimateControlConfig.model_validate(translated).model_dump(mode="json")

    def lighting_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("mode") == "advanced":
            return LightControlConfig.model_validate(payload["advanced"]).model_dump(mode="json")
        _require_keys(payload, ["start", "end"])
        translated = {
            "actuator": payload.get("actuator", "lamps"),
            "schedule": {
                "start": payload["start"],
                "end": payload["end"],
            },
        }
        return LightControlConfig.model_validate(translated).model_dump(mode="json")

    def watering_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("mode") == "advanced":
            return WateringControlConfig.model_validate(payload["advanced"]).model_dump(mode="json")
        _require_keys(payload, ["watering_mode"])

        translated: dict[str, Any] = {
            "actuator": payload.get("actuator", "water_pump"),
            "mode": payload["watering_mode"],
        }
        if payload["watering_mode"] == "schedule":
            _require_keys(payload, ["interval_minutes", "run_seconds", "anchor"])
            translated["schedule"] = {
                "interval_minutes": payload["interval_minutes"],
                "run_seconds": payload["run_seconds"],
                "anchor": payload["anchor"],
            }
        else:
            _require_keys(payload, ["start_below", "stop_above"])
            if payload["stop_above"] <= payload["start_below"]:
                raise ValueError("stop_above must be greater than start_below")
            translated["sensor"] = {
                "sensor": payload.get("sensor", "soil_tray_1"),
                "metric": payload.get("metric", "moisture_pct"),
                "start_below": payload["start_below"],
                "stop_above": payload["stop_above"],
                "max_run_seconds": payload.get("max_run_seconds"),
            }
        return WateringControlConfig.model_validate(translated).model_dump(mode="json")

    def emergency_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("mode") == "advanced":
            return EmergencyControlConfig.model_validate(payload["advanced"]).model_dump(mode="json")
        _require_keys(payload, ["high_temp", "high_humidity"])
        off_actions = []
        if payload.get("lamps_off", True):
            off_actions.append(
                {
                    "actuator": payload.get("lamps_actuator", "lamps"),
                    "command": {"power": False},
                }
            )
        if payload.get("pads_off", True):
            off_actions.append(
                {
                    "actuator": payload.get("pads_actuator", "warm_pads"),
                    "command": {"power": False},
                }
            )
        if payload.get("pump_off", False):
            off_actions.append(
                {
                    "actuator": payload.get("pump_actuator", "water_pump"),
                    "command": {"power": False},
                }
            )
        translated = {
            "when": {
                "any": [
                    {
                        "sensor": payload.get("temp_sensor", "air_lab"),
                        "metric": "temperature_c",
                        "op": ">=",
                        "value": payload["high_temp"],
                    },
                    {
                        "sensor": payload.get("humidity_sensor", "air_lab"),
                        "metric": "humidity_pct",
                        "op": ">=",
                        "value": payload["high_humidity"],
                    },
                ]
            },
            "actions": {
                "on": [
                    {
                        "actuator": payload.get("fan_actuator", "exhaust_fan"),
                        "command": {"power": payload.get("fan_on", True)},
                    }
                ],
                "off": off_actions,
            },
        }
        return EmergencyControlConfig.model_validate(translated).model_dump(mode="json")


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(payload, sort_keys=False)
    path.write_text(text, encoding="utf-8")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _diff_dict(base: dict[str, Any], effective: dict[str, Any]) -> dict[str, Any]:
    diff: dict[str, Any] = {}
    for key, value in effective.items():
        if isinstance(value, dict):
            nested = _diff_dict(base.get(key, {}) if isinstance(base.get(key), dict) else {}, value)
            if nested:
                diff[key] = nested
        elif base.get(key) != value:
            diff[key] = value
    return diff


def _require_keys(payload: dict[str, Any], keys: list[str]) -> None:
    missing = [key for key in keys if key not in payload or payload[key] is None]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
