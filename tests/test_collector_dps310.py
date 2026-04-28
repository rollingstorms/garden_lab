from __future__ import annotations

from growlab.collector.drivers.sensor import i2c_dps310


def _encode_twos_complement(value: int, bits: int) -> int:
    if value < 0:
        value += 1 << bits
    return value


def _pack_coefficients(coefficients: dict[str, int]) -> list[int]:
    c0 = _encode_twos_complement(coefficients["c0"], 12)
    c1 = _encode_twos_complement(coefficients["c1"], 12)
    c00 = _encode_twos_complement(coefficients["c00"], 20)
    c10 = _encode_twos_complement(coefficients["c10"], 20)
    c01 = _encode_twos_complement(coefficients["c01"], 16)
    c11 = _encode_twos_complement(coefficients["c11"], 16)
    c20 = _encode_twos_complement(coefficients["c20"], 16)
    c21 = _encode_twos_complement(coefficients["c21"], 16)
    c30 = _encode_twos_complement(coefficients["c30"], 16)

    return [
        (c0 >> 4) & 0xFF,
        ((c0 & 0x0F) << 4) | ((c1 >> 8) & 0x0F),
        c1 & 0xFF,
        (c00 >> 12) & 0xFF,
        (c00 >> 4) & 0xFF,
        ((c00 & 0x0F) << 4) | ((c10 >> 16) & 0x0F),
        (c10 >> 8) & 0xFF,
        c10 & 0xFF,
        (c01 >> 8) & 0xFF,
        c01 & 0xFF,
        (c11 >> 8) & 0xFF,
        c11 & 0xFF,
        (c20 >> 8) & 0xFF,
        c20 & 0xFF,
        (c21 >> 8) & 0xFF,
        c21 & 0xFF,
        (c30 >> 8) & 0xFF,
        c30 & 0xFF,
    ]


def _pack_raw_24bit(value: int) -> list[int]:
    encoded = _encode_twos_complement(value, 24)
    return [(encoded >> 16) & 0xFF, (encoded >> 8) & 0xFF, encoded & 0xFF]


def test_dps310_driver_reads_temperature_and_pressure(monkeypatch) -> None:
    coefficients = {
        "c0": 200,
        "c1": 100,
        "c00": 100000,
        "c10": 20000,
        "c01": 0,
        "c11": 0,
        "c20": 0,
        "c21": 0,
        "c30": 0,
    }
    coefficient_bytes = _pack_coefficients(coefficients)
    pressure_raw = _pack_raw_24bit(253952)
    temperature_raw = _pack_raw_24bit(253952)

    class FakeSMBus:
        def __init__(self, bus_number: int) -> None:
            self.bus_number = bus_number
            self.writes: list[tuple[int, int, int]] = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def write_byte_data(self, address: int, register: int, value: int) -> None:
            self.writes.append((address, register, value))

        def read_byte_data(self, address: int, register: int) -> int:
            if register == 0x08:
                return 0xF0
            if register == 0x28:
                return 0x80
            raise AssertionError(f"unexpected register read: 0x{register:02x}")

        def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]:
            if register == 0x10 and length == 18:
                return coefficient_bytes
            if register == 0x00 and length == 6:
                return pressure_raw + temperature_raw
            raise AssertionError(f"unexpected block read: reg=0x{register:02x} len={length}")

    monkeypatch.setattr(i2c_dps310, "SMBus", FakeSMBus)
    monkeypatch.setattr(i2c_dps310.time, "sleep", lambda _: None)

    driver = i2c_dps310.DPS310Driver()
    driver.setup({"bus": 1, "address": 0x77, "pressure_oversampling": 4, "temperature_oversampling": 4})

    assert driver.read() == {"temperature_c": 200.0, "pressure_hpa": 1200.0}
