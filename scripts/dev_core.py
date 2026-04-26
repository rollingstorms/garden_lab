from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from growlab.core.app.main import app


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("GARDEN_LAB_HOST", "0.0.0.0")
    port = int(os.environ.get("GARDEN_LAB_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
