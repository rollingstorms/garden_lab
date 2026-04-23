from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from typing import Optional

from growlab.core.config.models import GrowLabConfig
from growlab.collector.ingestion_client import IngestionClient
from growlab.shared.time import utc_now


@dataclass
class PollingResult:
    scheduled_sensor_count: int
    posted_sensor_count: int
    heartbeat_sent: bool
    errors: list[str]


class PollingService:
    def __init__(self, *, config: GrowLabConfig) -> None:
        self.config = config
        self.client = IngestionClient(config.app.ingest_base_url)

    def _load_sensor_driver(self, driver_name: str):
        driver_path = self.config.drivers.collector_sensor[driver_name]
        module_name, class_name = driver_path.split(":", maxsplit=1)
        module = importlib.import_module(module_name)
        driver_cls = getattr(module, class_name)
        return driver_cls()

    def run_once(self, *, sensor_ids: Optional[set[str]] = None) -> dict:
        collector_sensors = {
            sensor_id: sensor
            for sensor_id, sensor in self.config.sensors.items()
            if sensor.source.kind == "collector"
            and (sensor_ids is None or sensor_id in sensor_ids)
        }
        errors: list[str] = []
        posted_sensor_count = 0
        collector_ids = set()

        for sensor_id, sensor in collector_sensors.items():
            source = sensor.source
            collector_ids.add(source.collector_id)
            try:
                driver = self._load_sensor_driver(source.driver)
                driver.setup(source.config)
                metrics = driver.read()
                response = self.client.post_sensor_metrics(
                    sensor_id=sensor_id,
                    ts_utc=utc_now(),
                    metrics=metrics,
                )
                response.raise_for_status()
                posted_sensor_count += 1
            except Exception as exc:  # pragma: no cover - exercised by runtime integration
                errors.append(f"{sensor_id}: {exc}")

        heartbeat_sent = False
        for collector_id in sorted(collector_ids):
            try:
                response = self.client.post_collector_heartbeat(
                    collector_id=collector_id,
                    ts_utc=utc_now(),
                    status="degraded" if errors else "ok",
                    payload={
                        "scheduled_sensor_count": len(collector_sensors),
                        "posted_sensor_count": posted_sensor_count,
                        "errors": errors,
                    },
                )
                response.raise_for_status()
                heartbeat_sent = True
            except Exception as exc:  # pragma: no cover - exercised by runtime integration
                errors.append(f"heartbeat[{collector_id}]: {exc}")

        result = PollingResult(
            scheduled_sensor_count=len(collector_sensors),
            posted_sensor_count=posted_sensor_count,
            heartbeat_sent=heartbeat_sent,
            errors=errors,
        )
        return {
            "scheduled_sensor_count": result.scheduled_sensor_count,
            "posted_sensor_count": result.posted_sensor_count,
            "heartbeat_sent": result.heartbeat_sent,
            "errors": result.errors,
        }

    def run_forever(self) -> None:
        collector_sensors = {
            sensor_id: sensor
            for sensor_id, sensor in self.config.sensors.items()
            if sensor.source.kind == "collector"
        }
        if not collector_sensors:
            time.sleep(5)
            return

        next_due = {sensor_id: 0.0 for sensor_id in collector_sensors}
        while True:
            now = time.monotonic()
            due_sensor_ids = [
                sensor_id
                for sensor_id, sensor in collector_sensors.items()
                if now >= next_due[sensor_id]
                and sensor.enabled
            ]

            if due_sensor_ids:
                self.run_once(sensor_ids=set(due_sensor_ids))
                now = time.monotonic()
                for sensor_id, sensor in collector_sensors.items():
                    if sensor_id in due_sensor_ids:
                        next_due[sensor_id] = now + sensor.source.poll.every_seconds

            enabled_sensor_ids = [
                sensor_id
                for sensor_id, sensor in collector_sensors.items()
                if sensor.enabled
            ]
            if not enabled_sensor_ids:
                time.sleep(5)
                continue

            sleep_for = min(
                max(next_due[sensor_id] - time.monotonic(), 1.0)
                for sensor_id in enabled_sensor_ids
            )
            time.sleep(sleep_for)
