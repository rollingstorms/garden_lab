from __future__ import annotations

import time
from typing import Any, Union

try:
    from smbus2 import SMBus
except ImportError:  # pragma: no cover - depends on runtime environment
    SMBus = None

# Register map
_CMD_BIT = 0x80       # command flag
_CMD_AUTO = 0xA0      # command + auto-increment (for multi-byte reads)
_REG_ENABLE = 0x00
_REG_CONTROL = 0x01
_REG_CHAN0_LOW = 0x14  # CH0: full spectrum (visible + IR), 2 bytes
# CH1 follows immediately at 0x16 (IR only)

_ALS_ON = 0x03   # PON | AEN
_ALS_OFF = 0x00

# Integration time setting -> milliseconds
_ATIME_MS: dict[int, int] = {0: 100, 1: 200, 2: 300, 3: 400, 4: 500, 5: 600}

# Gain setting (upper nibble of control register) -> multiplier
_AGAIN: dict[int, int] = {0: 1, 1: 25, 2: 428, 3: 9876}

_LUX_DF = 408.0  # lux coefficient from datasheet


class TSL2591Driver:
    """I2C driver for the TSL2591 ambient light sensor.

    Config keys (all optional):
        bus          int   I2C bus number (default 1)
        address      int   I2C address in decimal (default 41 = 0x29)
        gain         int   0=1x  1=25x  2=428x  3=9876x  (default 1 = 25x)
        integration  int   0-5, maps to 100-600 ms integration time (default 1 = 200ms)
    """

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def setup(self, config: dict[str, Any]) -> None:
        self._config = config

    def read(self) -> dict[str, Union[float, int, str, bool, None]]:
        if SMBus is None:
            raise RuntimeError("smbus2 is required for the TSL2591 collector driver")

        bus_number = int(self._config.get("bus", 1))
        address = int(self._config.get("address", 0x29))
        gain = int(self._config.get("gain", 1))          # default 25x
        integration = int(self._config.get("integration", 1))  # default 200ms

        atime_ms = _ATIME_MS[integration]
        again = _AGAIN[gain]

        with SMBus(bus_number) as bus:
            # Power on and enable ALS
            bus.write_byte_data(address, _CMD_BIT | _REG_ENABLE, _ALS_ON)
            # Set gain and integration time
            bus.write_byte_data(address, _CMD_BIT | _REG_CONTROL, (gain << 4) | integration)
            # Wait for one full integration cycle plus a small margin
            time.sleep((atime_ms + 10) / 1000.0)
            # Read 4 bytes: CH0_LOW, CH0_HIGH, CH1_LOW, CH1_HIGH
            data = bus.read_i2c_block_data(address, _CMD_AUTO | _REG_CHAN0_LOW, 4)
            # Power off to reduce self-heating
            bus.write_byte_data(address, _CMD_BIT | _REG_ENABLE, _ALS_OFF)

        ch0 = (data[1] << 8) | data[0]  # full spectrum
        ch1 = (data[3] << 8) | data[2]  # IR only

        # Saturated — return sentinel values rather than garbage lux
        if ch0 == 0xFFFF or ch1 == 0xFFFF:
            return {"lux": None, "visible": None, "infrared": ch1}

        cpl = (atime_ms * again) / _LUX_DF
        lux1 = (ch0 - 1.64 * ch1) / cpl
        lux2 = (0.59 * ch0 - 0.86 * ch1) / cpl
        lux = max(lux1, lux2, 0.0)

        return {
            "lux": round(lux, 2),
            "visible": ch0 - ch1,
            "infrared": ch1,
        }

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok" if self._config else "unknown",
            "configured": bool(self._config),
            "driver": "i2c_tsl2591",
        }
