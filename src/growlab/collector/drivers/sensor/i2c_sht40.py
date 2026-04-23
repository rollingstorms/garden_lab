from __future__ import annotations

import time
from typing import Any, Union

try:
    from smbus2 import SMBus, i2c_msg
except ImportError:  # pragma: no cover - depends on runtime environment
    SMBus = None
    i2c_msg = None


class SHT40Driver:
    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def setup(self, config: dict[str, Any]) -> None:
        self._config = config

    def read(self) -> dict[str, Union[float, int, str, bool, None]]:
        if SMBus is None or i2c_msg is None:
            raise RuntimeError("smbus2 is required for the SHT40 collector driver")

        bus_number = int(self._config.get("bus", 1))
        address = int(self._config.get("address", 0x44))
        measure_cmd = int(self._config.get("measure_cmd", 0xFD))
        delay_seconds = float(self._config.get("delay_seconds", 0.02))

        with SMBus(bus_number) as bus:
            write = i2c_msg.write(address, [measure_cmd])
            bus.i2c_rdwr(write)
            time.sleep(delay_seconds)
            read = i2c_msg.read(address, 6)
            bus.i2c_rdwr(read)
            data = list(read)

        t_raw = (data[0] << 8) | data[1]
        h_raw = (data[3] << 8) | data[4]
        temperature_c = -45 + (175 * t_raw / 65535)
        humidity_pct = 100 * (h_raw / 65535)
        return {"temperature_c": temperature_c, "humidity_pct": humidity_pct}

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok" if self._config else "unknown",
            "configured": bool(self._config),
            "driver": "i2c_sht40",
        }
