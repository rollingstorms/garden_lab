from __future__ import annotations

import time
from typing import Any, Union

try:
    from smbus2 import SMBus
except ImportError:  # pragma: no cover - depends on runtime environment
    SMBus = None


_REG_PRS_B2 = 0x00
_REG_TMP_B2 = 0x03
_REG_PRS_CFG = 0x06
_REG_TMP_CFG = 0x07
_REG_MEAS_CFG = 0x08
_REG_CFG_REG = 0x09
_REG_RESET = 0x0C
_REG_COEF = 0x10
_REG_TMP_COEF_SRCE = 0x28

_MEAS_CTRL_IDLE = 0x00
_MEAS_CTRL_CONTINUOUS_BOTH = 0x07

_MEAS_CFG_COEF_RDY = 1 << 7
_MEAS_CFG_SENSOR_RDY = 1 << 6
_MEAS_CFG_TMP_RDY = 1 << 5
_MEAS_CFG_PRS_RDY = 1 << 4

_CFG_T_SHIFT = 1 << 3
_CFG_P_SHIFT = 1 << 2

_TMP_COEF_SRCE_EXT = 1 << 7
_RESET_SOFT_RST = 0x09

_SCALE_FACTORS = (
    524288.0,
    1572864.0,
    3670016.0,
    7864320.0,
    253952.0,
    516096.0,
    1040384.0,
    2088960.0,
)


def _sign_extend(value: int, bits: int) -> int:
    sign_bit = 1 << (bits - 1)
    return value - (1 << bits) if value & sign_bit else value


class DPS310Driver:
    def __init__(self) -> None:
        self._config: dict[str, Any] = {}
        self._coefficients: dict[str, int] = {}
        self._temperature_source = 0

    def setup(self, config: dict[str, Any]) -> None:
        if SMBus is None:
            raise RuntimeError("smbus2 is required for the DPS310 collector driver")

        self._config = config
        with SMBus(self._bus_number) as bus:
            if bool(config.get("reset", True)):
                bus.write_byte_data(self._address, _REG_RESET, _RESET_SOFT_RST)
                time.sleep(float(config.get("reset_delay_seconds", 0.04)))

            self._wait_for_ready(
                bus,
                mask=_MEAS_CFG_SENSOR_RDY | _MEAS_CFG_COEF_RDY,
                timeout_seconds=float(config.get("startup_timeout_seconds", 0.5)),
            )
            self._temperature_source = bus.read_byte_data(self._address, _REG_TMP_COEF_SRCE) & _TMP_COEF_SRCE_EXT
            raw_coefficients = bus.read_i2c_block_data(self._address, _REG_COEF, 18)
            self._coefficients = self._parse_coefficients(raw_coefficients)

    def read(self) -> dict[str, Union[float, int, str, bool, None]]:
        if SMBus is None:
            raise RuntimeError("smbus2 is required for the DPS310 collector driver")
        if not self._coefficients:
            raise RuntimeError("DPS310 driver must be set up before read()")

        pressure_rate = self._bounded_bits("pressure_rate", default=1)
        pressure_oversampling = self._bounded_bits("pressure_oversampling", default=4)
        temperature_rate = self._bounded_bits("temperature_rate", default=1)
        temperature_oversampling = self._bounded_bits("temperature_oversampling", default=4)

        prs_cfg = (pressure_rate << 4) | pressure_oversampling
        tmp_cfg = self._temperature_source | (temperature_rate << 4) | temperature_oversampling

        cfg_reg = 0
        if pressure_oversampling > 3:
            cfg_reg |= _CFG_P_SHIFT
        if temperature_oversampling > 3:
            cfg_reg |= _CFG_T_SHIFT

        with SMBus(self._bus_number) as bus:
            bus.write_byte_data(self._address, _REG_PRS_CFG, prs_cfg)
            bus.write_byte_data(self._address, _REG_TMP_CFG, tmp_cfg)
            bus.write_byte_data(self._address, _REG_CFG_REG, cfg_reg)
            bus.write_byte_data(self._address, _REG_MEAS_CFG, _MEAS_CTRL_CONTINUOUS_BOTH)

            self._wait_for_ready(
                bus,
                mask=_MEAS_CFG_PRS_RDY | _MEAS_CFG_TMP_RDY,
                timeout_seconds=float(self._config.get("ready_timeout_seconds", 0.5)),
                poll_interval_seconds=float(self._config.get("poll_interval_seconds", 0.01)),
            )
            raw_data = bus.read_i2c_block_data(self._address, _REG_PRS_B2, 6)
            bus.write_byte_data(self._address, _REG_MEAS_CFG, _MEAS_CTRL_IDLE)

        pressure_raw = self._read_24bit(raw_data[0:3])
        temperature_raw = self._read_24bit(raw_data[3:6])

        pressure_scale = _SCALE_FACTORS[pressure_oversampling]
        temperature_scale = _SCALE_FACTORS[temperature_oversampling]
        pressure_scaled = pressure_raw / pressure_scale
        temperature_scaled = temperature_raw / temperature_scale

        coefficients = self._coefficients
        temperature_c = coefficients["c0"] * 0.5 + coefficients["c1"] * temperature_scaled
        pressure_pa = (
            coefficients["c00"]
            + pressure_scaled
            * (
                coefficients["c10"]
                + pressure_scaled * (coefficients["c20"] + pressure_scaled * coefficients["c30"])
            )
            + temperature_scaled * coefficients["c01"]
            + temperature_scaled
            * pressure_scaled
            * (coefficients["c11"] + pressure_scaled * coefficients["c21"])
        )

        return {
            "temperature_c": round(temperature_c, 2),
            "pressure_hpa": round(pressure_pa / 100.0, 2),
        }

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok" if self._config and self._coefficients else "unknown",
            "configured": bool(self._config),
            "driver": "i2c_dps310",
            "bus": self._config.get("bus", 1),
            "address": self._config.get("address", 0x77),
        }

    @property
    def _bus_number(self) -> int:
        return int(self._config.get("bus", 1))

    @property
    def _address(self) -> int:
        return int(self._config.get("address", 0x77))

    def _bounded_bits(self, key: str, *, default: int) -> int:
        value = int(self._config.get(key, default))
        if value < 0 or value > 7:
            raise ValueError(f"{key} must be between 0 and 7 for DPS310")
        return value

    def _wait_for_ready(
        self,
        bus: SMBus,
        *,
        mask: int,
        timeout_seconds: float,
        poll_interval_seconds: float = 0.01,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            meas_cfg = bus.read_byte_data(self._address, _REG_MEAS_CFG)
            if meas_cfg & mask == mask:
                return
            time.sleep(poll_interval_seconds)
        raise TimeoutError(f"DPS310 did not become ready for mask 0x{mask:02x}")

    @staticmethod
    def _read_24bit(data: list[int]) -> int:
        return _sign_extend((data[0] << 16) | (data[1] << 8) | data[2], 24)

    @staticmethod
    def _parse_coefficients(raw: list[int]) -> dict[str, int]:
        if len(raw) != 18:
            raise ValueError("DPS310 coefficient block must be 18 bytes")

        return {
            "c0": _sign_extend((raw[0] << 4) | (raw[1] >> 4), 12),
            "c1": _sign_extend(((raw[1] & 0x0F) << 8) | raw[2], 12),
            "c00": _sign_extend((raw[3] << 12) | (raw[4] << 4) | (raw[5] >> 4), 20),
            "c10": _sign_extend(((raw[5] & 0x0F) << 16) | (raw[6] << 8) | raw[7], 20),
            "c01": _sign_extend((raw[8] << 8) | raw[9], 16),
            "c11": _sign_extend((raw[10] << 8) | raw[11], 16),
            "c20": _sign_extend((raw[12] << 8) | raw[13], 16),
            "c21": _sign_extend((raw[14] << 8) | raw[15], 16),
            "c30": _sign_extend((raw[16] << 8) | raw[17], 16),
        }
