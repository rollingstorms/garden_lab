from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from growlab.core.config.models import AutomationConfig
from growlab.core.services.garden import (
    ActuatorRuntimeState,
    GardenController,
    GardenRuntimeState,
)


def build_automation(data: dict) -> AutomationConfig:
    return AutomationConfig.model_validate(data)


def test_garden_emergency_overrides_light_and_heat() -> None:
    automation = build_automation(
        {
            "mode": "garden_v1",
            "controller": {
                "climate": {
                    "fan": {
                        "actuator": "exhaust_fan",
                        "bands": [
                            {
                                "sensor": "air_lab",
                                "metric": "temperature_c",
                                "on_above": 28.0,
                                "off_below": 25.5,
                            }
                        ],
                    },
                    "heat": {
                        "actuator": "warm_pads",
                        "bands": [
                            {
                                "sensor": "air_lab",
                                "metric": "temperature_c",
                                "on_below": 20.0,
                                "off_above": 22.0,
                            }
                        ],
                    },
                },
                "light": {
                    "actuator": "lamps",
                    "schedule": {"start": "06:00", "end": "22:00"},
                },
                "emergency": {
                    "when": {
                        "any": [
                            {
                                "sensor": "air_lab",
                                "metric": "temperature_c",
                                "op": ">=",
                                "value": 34.0,
                            }
                        ]
                    },
                    "actions": {
                        "on": [{"actuator": "exhaust_fan", "command": {"power": True}}],
                        "off": [
                            {"actuator": "warm_pads", "command": {"power": False}},
                            {"actuator": "lamps", "command": {"power": False}},
                        ],
                    },
                },
            },
        }
    )
    runtime = GardenRuntimeState(
        sensors={
            ("air_lab", "temperature_c"): 35.0,
        },
        actuators={
            "exhaust_fan": ActuatorRuntimeState(power=False),
            "warm_pads": ActuatorRuntimeState(power=True),
            "lamps": ActuatorRuntimeState(power=True),
        },
    )

    evaluation = GardenController().evaluate(
        automation_id="garden_equilibrium",
        automation=automation,
        runtime=runtime,
        now_utc=datetime(2026, 4, 24, 15, 0, tzinfo=timezone.utc),
        now_local=datetime(2026, 4, 24, 11, 0, tzinfo=ZoneInfo("America/New_York")),
    )

    commands = {item.actuator_id: item.command["power"] for item in evaluation.commands}
    assert evaluation.reason == "garden_emergency"
    assert commands == {
        "exhaust_fan": True,
        "lamps": False,
        "warm_pads": False,
    }


def test_garden_schedule_and_sensor_watering_modes() -> None:
    automation = build_automation(
        {
            "mode": "garden_v1",
            "controller": {
                "light": {
                    "actuator": "lamps",
                    "schedule": {"start": "06:00", "end": "22:00"},
                },
                "watering": {
                    "actuator": "water_pump",
                    "mode": "sensor",
                    "sensor": {
                        "sensor": "soil_tray_1",
                        "metric": "moisture_pct",
                        "start_below": 35.0,
                        "stop_above": 45.0,
                    },
                },
            },
        }
    )
    runtime = GardenRuntimeState(
        sensors={
            ("soil_tray_1", "moisture_pct"): 30.0,
        },
        actuators={
            "water_pump": ActuatorRuntimeState(power=False),
            "lamps": ActuatorRuntimeState(power=False),
        },
    )

    evaluation = GardenController().evaluate(
        automation_id="garden_equilibrium",
        automation=automation,
        runtime=runtime,
        now_utc=datetime(2026, 4, 24, 10, 0, tzinfo=timezone.utc),
        now_local=datetime(2026, 4, 24, 6, 0, tzinfo=ZoneInfo("America/New_York")),
    )

    commands = {item.actuator_id: item.command["power"] for item in evaluation.commands}
    assert commands["lamps"] is True
    assert commands["water_pump"] is True
