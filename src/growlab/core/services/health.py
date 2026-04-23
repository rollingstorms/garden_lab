from __future__ import annotations


class HealthService:
    def snapshot(self) -> dict:
        return {"status": "ok"}
