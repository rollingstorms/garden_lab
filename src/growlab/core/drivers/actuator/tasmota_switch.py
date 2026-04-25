from __future__ import annotations

from typing import Any

import httpx


class TasmotaSwitchDriver:
    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def setup(self, config: dict[str, Any]) -> None:
        self._config = config

    def get_state(self) -> dict[str, Any]:
        if not self._config:
            return {"status": "unknown", "driver": "tasmota_switch", "configured": False}

        try:
            response = self._send_command(self._power_command_name())
            result = response.get("StatusSNS", response)
            power_value = self._extract_power_value(result)
            return {
                "status": "ok",
                "driver": "tasmota_switch",
                "configured": True,
                "result": result,
                "state": {"power": power_value},
            }
        except Exception as exc:  # pragma: no cover - hardware/network runtime
            return {"status": "error", "driver": "tasmota_switch", "error": str(exc)}

    def apply(self, command: dict[str, Any]) -> dict[str, Any]:
        power_value = command.get("power")
        if power_value is None:
            return {
                "accepted": False,
                "driver": "tasmota_switch",
                "error": "missing_power_command",
                "command": command,
            }

        try:
            target = "On" if bool(power_value) else "Off"
            result = self._send_command(f"{self._power_command_name()} {target}")
            return {
                "accepted": True,
                "driver": "tasmota_switch",
                "command": command,
                "result": result,
                "state": {"power": bool(power_value)},
            }
        except Exception as exc:  # pragma: no cover - hardware/network runtime
            return {
                "accepted": False,
                "driver": "tasmota_switch",
                "error": str(exc),
                "command": command,
            }

    def health(self) -> dict[str, Any]:
        if not self._config:
            return {"status": "unknown", "configured": False}
        return {
            "status": "ok",
            "configured": True,
            "driver": "tasmota_switch",
            "endpoint": self._base_url(),
        }

    def _send_command(self, cmnd: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self._base_url()}/cm",
            params={"cmnd": cmnd},
            auth=self._auth(),
            timeout=self._timeout_seconds(),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected response payload: {payload!r}")
        return payload

    def _base_url(self) -> str:
        host = self._config.get("host") or self._config.get("ip")
        if not host:
            raise ValueError("Missing Tasmota host/ip")
        scheme = self._config.get("scheme", "http")
        return f"{scheme}://{host}"

    def _auth(self) -> tuple[str, str] | None:
        username = self._config.get("username")
        password = self._config.get("password")
        if username and password:
            return (str(username), str(password))
        return None

    def _timeout_seconds(self) -> float:
        value = self._config.get("timeout_seconds", 5)
        return float(value)

    def _power_command_name(self) -> str:
        relay = self._config.get("relay")
        if relay in (None, "", 1, "1"):
            return "Power"
        return f"Power{relay}"

    def _extract_power_value(self, payload: dict[str, Any]) -> bool | None:
        for key in (self._power_command_name(), "POWER", "Power"):
            if key not in payload:
                continue
            value = payload[key]
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                upper = value.strip().upper()
                if upper in {"ON", "1", "TRUE"}:
                    return True
                if upper in {"OFF", "0", "FALSE"}:
                    return False
        return None
