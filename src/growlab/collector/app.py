from __future__ import annotations

import os
from pathlib import Path

from growlab.core.config.loader import load_config
from growlab.collector.services.polling import PollingService


def run() -> None:
    base = Path(os.environ.get("GROWLAB_CONFIG_BASE", "config/base.yaml"))
    local = Path(os.environ.get("GROWLAB_CONFIG_LOCAL", "config/local.yaml"))
    config = load_config(base, local)
    PollingService(config=config).run_forever()


if __name__ == "__main__":
    run()
