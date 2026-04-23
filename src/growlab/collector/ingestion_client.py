from __future__ import annotations

from datetime import datetime

import httpx


class IngestionClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def post_sensor_metrics(
        self,
        *,
        sensor_id: str,
        ts_utc: datetime,
        metrics: dict,
    ) -> httpx.Response:
        with httpx.Client(timeout=10.0) as client:
            return client.post(
                f"{self.base_url}/api/ingest/sensors/{sensor_id}",
                json={"ts_utc": ts_utc.isoformat(), "metrics": metrics},
            )

    def post_collector_heartbeat(
        self,
        *,
        collector_id: str,
        ts_utc: datetime,
        status: str,
        payload: dict,
    ) -> httpx.Response:
        with httpx.Client(timeout=10.0) as client:
            return client.post(
                f"{self.base_url}/api/collectors/{collector_id}/heartbeat",
                json={"ts_utc": ts_utc.isoformat(), "status": status, "payload": payload},
            )
