from __future__ import annotations

from typing import Any


class GPIORelayDriver:
    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def setup(self, config: dict[str, Any]) -> None:
        self._config = config

    def get_state(self) -> dict[str, Any]:
        return {"status": "unimplemented", "driver": "gpio_relay"}

    def apply(self, command: dict[str, Any]) -> dict[str, Any]:
        return {"accepted": True, "command": command, "driver": "gpio_relay"}

    def health(self) -> dict[str, Any]:
        return {"status": "unknown", "configured": bool(self._config)}
