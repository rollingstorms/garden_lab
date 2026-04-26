from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aioesphomeapi import APIClient


class ESPHomeSwitchDriver:
    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def setup(self, config: dict[str, Any]) -> None:
        self._config = config

    def get_state(self) -> dict[str, Any]:
        if not self._config:
            return {"status": "unknown", "driver": "esphome_switch", "configured": False}

        try:
            result = asyncio.run(self._read_state())
            return {
                "status": "ok",
                "driver": "esphome_switch",
                "configured": True,
                "state": {"power": result["state"]},
                "entity": result["entity"],
            }
        except Exception as exc:  # pragma: no cover - hardware/network runtime
            return {"status": "error", "driver": "esphome_switch", "error": str(exc)}

    def apply(self, command: dict[str, Any]) -> dict[str, Any]:
        power_value = command.get("power")
        if power_value is None:
            return {
                "accepted": False,
                "driver": "esphome_switch",
                "error": "missing_power_command",
                "command": command,
            }

        try:
            result = asyncio.run(self._set_state(bool(power_value)))
            return {
                "accepted": True,
                "driver": "esphome_switch",
                "command": command,
                "state": {"power": result["state"]},
                "entity": result["entity"],
            }
        except Exception as exc:  # pragma: no cover - hardware/network runtime
            return {
                "accepted": False,
                "driver": "esphome_switch",
                "error": str(exc),
                "command": command,
            }

    def health(self) -> dict[str, Any]:
        if not self._config:
            return {"status": "unknown", "configured": False}
        return {
            "status": "ok",
            "configured": True,
            "driver": "esphome_switch",
            "host": self._address(),
            "port": self._port(),
            "switch_object_id": self._switch_object_id(),
        }

    async def _read_state(self) -> dict[str, Any]:
        return await self._with_client(self._get_switch_state)

    async def _set_state(self, power: bool) -> dict[str, Any]:
        async def runner(client: APIClient) -> dict[str, Any]:
            entity = await self._find_switch_entity(client)
            state_task = asyncio.create_task(self._await_switch_state(client, entity["key"]))
            client.switch_command(entity["key"], power)
            state = await state_task
            return {"state": state, "entity": entity}

        return await self._with_client(runner)

    async def _get_switch_state(self, client: APIClient) -> dict[str, Any]:
        entity = await self._find_switch_entity(client)
        state = await self._await_switch_state(client, entity["key"])
        return {"state": state, "entity": entity}

    async def _with_client(
        self,
        runner: Callable[[APIClient], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        client = APIClient(
            self._address(),
            self._port(),
            self._password(),
            noise_psk=self._noise_psk(),
            expected_name=self._expected_name(),
        )
        await asyncio.wait_for(client.connect(login=True), timeout=8.0)
        try:
            return await asyncio.wait_for(runner(client), timeout=8.0)
        finally:
            await client.disconnect()

    async def _find_switch_entity(self, client: APIClient) -> dict[str, Any]:
        entities, _ = await client.list_entities_services()
        target_object_id = self._switch_object_id()
        for entity in entities:
            if type(entity).__name__ != "SwitchInfo":
                continue
            if getattr(entity, "object_id", None) == target_object_id:
                return {
                    "key": getattr(entity, "key"),
                    "object_id": getattr(entity, "object_id"),
                    "name": getattr(entity, "name"),
                }
        raise ValueError(f"Switch entity not found: {target_object_id}")

    async def _await_switch_state(self, client: APIClient, key: int) -> bool:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()

        def on_state(state: Any) -> None:
            if getattr(state, "key", None) != key or future.done():
                return
            future.set_result(bool(getattr(state, "state")))

        client.subscribe_states(on_state)
        return await asyncio.wait_for(future, timeout=self._state_timeout_seconds())

    def _address(self) -> str:
        address = self._config.get("host") or self._config.get("ip")
        if not address:
            raise ValueError("Missing ESPHome host/ip")
        return str(address)

    def _port(self) -> int:
        return int(self._config.get("port", 6053))

    def _password(self) -> str | None:
        password = self._config.get("password")
        return str(password) if password else None

    def _noise_psk(self) -> str | None:
        key = self._config.get("noise_psk")
        return str(key) if key else None

    def _expected_name(self) -> str | None:
        value = self._config.get("expected_name")
        return str(value) if value else None

    def _switch_object_id(self) -> str:
        return str(self._config.get("switch_object_id", "kauf_plug"))

    def _state_timeout_seconds(self) -> float:
        return float(self._config.get("state_timeout_seconds", 5))
