from __future__ import annotations

from typing import Any, Union


class BME280Driver:
    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def setup(self, config: dict[str, Any]) -> None:
        self._config = config

    def read(self) -> dict[str, Union[float, int, str, bool, None]]:
        return {"temperature_c": 0.0, "humidity_pct": 0.0, "pressure_hpa": 0.0}

    def health(self) -> dict[str, Any]:
        return {"status": "unknown", "configured": bool(self._config)}
