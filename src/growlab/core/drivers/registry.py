from __future__ import annotations

import importlib

from growlab.core.config.models import GrowLabConfig


def load_actuator_driver(config: GrowLabConfig, driver_name: str):
    driver_path = config.drivers.actuator[driver_name]
    module_name, class_name = driver_path.split(":", maxsplit=1)
    module = importlib.import_module(module_name)
    driver_cls = getattr(module, class_name)
    return driver_cls()
