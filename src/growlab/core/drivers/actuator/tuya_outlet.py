from __future__ import annotations

from typing import Any

try:
    from tinytuya import OutletDevice
except ImportError:  # pragma: no cover - runtime dependency
    OutletDevice = None


class TuyaOutletDriver:
    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def setup(self, config: dict[str, Any]) -> None:
        self._config = config

    def get_state(self) -> dict[str, Any]:
        if OutletDevice is None:
            return {
                "status": "unavailable",
                "driver": "tuya_outlet",
                "reason": "tinytuya_not_installed",
            }
        try:
            device = self._build_device()
            status = device.status()
            return {"status": "ok", "driver": "tuya_outlet", "result": status}
        except Exception as exc:  # pragma: no cover - hardware/network runtime
            return {"status": "error", "driver": "tuya_outlet", "error": str(exc)}

    def apply(self, command: dict[str, Any]) -> dict[str, Any]:
        power_value = command.get("power")
        if power_value is None:
            return {
                "accepted": False,
                "driver": "tuya_outlet",
                "error": "missing_power_command",
                "command": command,
            }

        if OutletDevice is None:
            return {
                "accepted": False,
                "driver": "tuya_outlet",
                "error": "tinytuya_not_installed",
                "command": command,
            }

        try:
            device = self._build_device()
            if bool(power_value):
                device.turn_on()
            else:
                device.turn_off()
            return {
                "accepted": True,
                "driver": "tuya_outlet",
                "command": command,
                "state": {"power": bool(power_value)},
            }
        except Exception as exc:  # pragma: no cover - hardware/network runtime
            return {
                "accepted": False,
                "driver": "tuya_outlet",
                "error": str(exc),
                "command": command,
            }

    def health(self) -> dict[str, Any]:
        if not self._config:
            return {"status": "unknown", "configured": False}
        return {
            "status": "ok" if OutletDevice is not None else "degraded",
            "configured": True,
            "driver": "tuya_outlet",
            "dependency": "tinytuya" if OutletDevice is not None else "missing",
        }

    def _build_device(self):
        return OutletDevice(
            dev_id=self._config["device_id"],
            address=self._config["ip"],
            local_key=self._config["local_key"],
            version=self._config.get("version", 3.4),
        )
