from __future__ import annotations

from sqlalchemy.orm import Session

from growlab.core.db.repo_events import insert_collector_heartbeat
from growlab.core.db.repo_readings import insert_sensor_metrics
from growlab.core.schemas.api import CollectorHeartbeatPayload, SensorIngestPayload


class IngestionService:
    def ingest_sensor_payload(
        self,
        session: Session,
        *,
        sensor_id: str,
        payload: SensorIngestPayload,
        source_kind: str,
        source_id: str,
    ) -> None:
        insert_sensor_metrics(
            session,
            sensor_id=sensor_id,
            ts_utc=payload.ts_utc,
            metrics=payload.metrics,
            source_kind=source_kind,
            source_id=source_id,
        )

    def record_collector_heartbeat(
        self,
        session: Session,
        *,
        collector_id: str,
        payload: CollectorHeartbeatPayload,
    ) -> None:
        insert_collector_heartbeat(
            session,
            collector_id=collector_id,
            ts_utc=payload.ts_utc,
            status=payload.status,
            payload=payload.payload,
        )
