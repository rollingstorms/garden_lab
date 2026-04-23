from __future__ import annotations

from growlab.shared.time import utc_now


def build_heartbeat(collector_id: str) -> dict:
    return {
        "collector_id": collector_id,
        "ts_utc": utc_now().isoformat(),
        "status": "ok",
    }
