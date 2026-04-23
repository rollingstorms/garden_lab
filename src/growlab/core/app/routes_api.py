from __future__ import annotations

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException

from growlab.core.app.dependencies import get_db_session, get_registry
from growlab.core.config.registry import EntityRegistry
from growlab.core.db.repo_events import get_latest_actuator_event, get_latest_automation_event
from growlab.core.db.repo_readings import get_latest_sensor_metrics, get_sensor_history
from growlab.core.schemas.api import (
    ActuatorCommandPayload,
    CollectorHeartbeatPayload,
    SensorIngestPayload,
)
from growlab.core.services.commands import CommandService
from growlab.core.services.ingestion import IngestionService
from growlab.core.services.automation import AutomationService

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/entities")
def entities(registry: EntityRegistry = Depends(get_registry)) -> dict:
    return {
        "sensors": list(registry.config.sensors.keys()),
        "actuators": list(registry.config.actuators.keys()),
        "automations": list(registry.config.automations.keys()),
        "dashboards": registry.dashboard_ids(),
    }


@router.post("/ingest/sensors/{sensor_id}")
def ingest_sensor(
    sensor_id: str,
    payload: SensorIngestPayload,
    registry: EntityRegistry = Depends(get_registry),
    session: Session = Depends(get_db_session),
) -> dict:
    sensor = registry.get_sensor(sensor_id)
    if sensor.source.kind == "collector":
        source_kind = "collector"
        source_id = sensor.source.collector_id
    else:
        source_kind = "remote"
        source_id = sensor_id
    IngestionService().ingest_sensor_payload(
        session,
        sensor_id=sensor_id,
        payload=payload,
        source_kind=source_kind,
        source_id=source_id,
    )
    session.commit()
    return {
        "accepted": True,
        "sensor_id": sensor_id,
        "metric_count": len(payload.metrics),
        "source_kind": source_kind,
        "source_id": source_id,
    }


@router.post("/collectors/{collector_id}/heartbeat")
def collector_heartbeat(
    collector_id: str,
    payload: CollectorHeartbeatPayload,
    registry: EntityRegistry = Depends(get_registry),
    session: Session = Depends(get_db_session),
) -> dict:
    if collector_id not in registry.config.collectors:
        raise HTTPException(status_code=404, detail=f"Unknown collector: {collector_id}")
    IngestionService().record_collector_heartbeat(session, collector_id=collector_id, payload=payload)
    session.commit()
    return {"accepted": True, "collector_id": collector_id, "status": payload.status}


@router.get("/sensors/{sensor_id}/latest")
def sensor_latest(
    sensor_id: str,
    registry: EntityRegistry = Depends(get_registry),
    session: Session = Depends(get_db_session),
) -> dict:
    sensor = registry.get_sensor(sensor_id)
    latest = get_latest_sensor_metrics(session, sensor_id=sensor_id)
    return {
        "sensor_id": sensor_id,
        "label": sensor.label,
        "metrics": list(sensor.metrics.keys()),
        "latest": latest,
    }


@router.get("/sensors/{sensor_id}/history")
def sensor_history_endpoint(
    sensor_id: str,
    metric: str,
    hours: int = 24,
    session: Session = Depends(get_db_session),
) -> dict:
    rows = get_sensor_history(session, sensor_id=sensor_id, metric=metric)
    return {
        "sensor_id": sensor_id,
        "metric": metric,
        "hours": hours,
        "points": [
            {
                "ts_utc": row.ts_utc.isoformat(),
                "value_num": row.value_num,
                "value_text": row.value_text,
                "source_kind": row.source_kind,
                "source_id": row.source_id,
            }
            for row in rows
        ],
    }


@router.get("/actuators/{actuator_id}/state")
def actuator_state(
    actuator_id: str,
    registry: EntityRegistry = Depends(get_registry),
    session: Session = Depends(get_db_session),
) -> dict:
    actuator = registry.get_actuator(actuator_id)
    latest_event = get_latest_actuator_event(session, actuator_id=actuator_id)
    return {
        "actuator_id": actuator_id,
        "driver": actuator.driver,
        "state": latest_event.payload_json.get("command", {}) if latest_event else {},
        "latest_event": {
            "event_type": latest_event.event_type,
            "status": latest_event.status,
            "ts_utc": latest_event.ts_utc.isoformat(),
        }
        if latest_event
        else None,
    }


@router.post("/actuators/{actuator_id}/commands")
def actuator_command(
    actuator_id: str,
    payload: ActuatorCommandPayload,
    registry: EntityRegistry = Depends(get_registry),
    session: Session = Depends(get_db_session),
) -> dict:
    result = CommandService().issue_command(
        registry=registry,
        session=session,
        actuator_id=actuator_id,
        payload=payload,
    )
    session.commit()
    return result


@router.get("/automations/{automation_id}")
def automation_detail(
    automation_id: str,
    registry: EntityRegistry = Depends(get_registry),
    session: Session = Depends(get_db_session),
) -> dict:
    automation = registry.config.automations[automation_id]
    latest_event = get_latest_automation_event(session, automation_id=automation_id)
    return {
        "automation_id": automation_id,
        "enabled": automation.enabled,
        "mode": automation.mode,
        "latest_event": {
            "decision": latest_event.decision,
            "reason": latest_event.reason,
            "ts_utc": latest_event.ts_utc.isoformat(),
        }
        if latest_event
        else None,
    }


@router.post("/automations/{automation_id}/enable")
def automation_enable(automation_id: str) -> dict:
    return {"automation_id": automation_id, "enabled": True}


@router.post("/automations/{automation_id}/disable")
def automation_disable(automation_id: str) -> dict:
    return {"automation_id": automation_id, "enabled": False}


@router.post("/automations/run")
def automations_run(
    registry: EntityRegistry = Depends(get_registry),
    session: Session = Depends(get_db_session),
) -> dict:
    result = AutomationService().run_cycle(registry=registry, session=session)
    session.commit()
    return result
