from __future__ import annotations


class CollectorHealthService:
    def snapshot(self) -> dict:
        return {"status": "ok"}
