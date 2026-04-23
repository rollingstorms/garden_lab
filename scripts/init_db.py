from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from growlab.core.config.loader import load_config
from growlab.core.db.models import Base
from growlab.core.db.session import build_engine


def main() -> None:
    base = Path(os.environ.get("GROWLAB_CONFIG_BASE", "config/base.yaml"))
    local = Path(os.environ.get("GROWLAB_CONFIG_LOCAL", "config/local.yaml"))
    config = load_config(base, local)
    engine = build_engine(config.app)
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    main()
