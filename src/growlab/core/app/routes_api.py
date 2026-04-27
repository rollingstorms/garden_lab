from __future__ import annotations

import os

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException

from growlab.core.app.dependencies import (
    get_actuator_state_service,
    get_dashboard_response_cache,
    get_db_session,
    get_registry,
)
from growlab.core.config.registry import EntityRegistry
from growlab.core.db.repo_events import get_latest_actuator_event, get_latest_automation_event
from growlab.core.db.repo_readings import get_latest_sensor_metrics, get_sensor_history
from growlab.core.schemas.api import (
    ActuatorCommandPayload,
    ClimateConfigPatchPayload,
    CollectorHeartbeatPayload,
    EmergencyConfigPatchPayload,
    GardenModuleEnabledPayload,
    LightingConfigPatchPayload,
    ManualOverridePayload,
    SensorIngestPayload,
    WateringConfigPatchPayload,
)
from growlab.core.services.commands import CommandService
from growlab.core.services.configuration import ConfigService, GardenSettingsTranslator
from growlab.core.services.ingestion import IngestionService
from growlab.core.services.automation import AutomationService
from growlab.core.services.garden_state import GardenStateService
from growlab.core.services.overrides import ManualOverrideService
from growlab.shared.time import utc_isoformat

router = APIRouter(prefix="/api")
STATE_CACHE_TTL_SECONDS = 2.0
HEAVY_CACHE_TTL_SECONDS = 20.0


def require_write_access() -> bool:
    token = os.environ.get("GARDEN_LAB_WRITE_TOKEN")
    if token:
        # Placeholder dependency so a real gate can be added without moving route logic.
        return True
    return True


def invalidate_dashboard_caches() -> None:
    get_dashboard_response_cache().invalidate_prefix(("garden",))


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
    invalidate_dashboard_caches()
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
    rows = get_sensor_history(session, sensor_id=sensor_id, metric=metric, hours=hours)
    return {
        "sensor_id": sensor_id,
        "metric": metric,
        "hours": hours,
        "points": [
            {
                "ts_utc": utc_isoformat(row.ts_utc),
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
    live_state = get_actuator_state_service().refresh_actuator(
        registry=registry,
        session=session,
        actuator_id=actuator_id,
    )
    session.commit()
    invalidate_dashboard_caches()
    return {
        "actuator_id": actuator_id,
        "driver": actuator.driver,
        "state": {"power": live_state.power},
        "driver_state": live_state.driver_state or {},
        "state_status": live_state.state_status,
        "state_source": live_state.state_source,
        "last_seen_at": live_state.last_seen_at,
        "error": live_state.error,
        "last_command": latest_event.payload_json.get("command", {}) if latest_event else {},
        "latest_event": {
            "event_type": latest_event.event_type,
            "status": latest_event.status,
            "ts_utc": utc_isoformat(latest_event.ts_utc),
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
    invalidate_dashboard_caches()
    return result


@router.get("/garden/state")
def garden_state(
    registry: EntityRegistry = Depends(get_registry),
    session: Session = Depends(get_db_session),
) -> dict:
    return get_dashboard_response_cache().get_or_set(
        ("garden", "state"),
        ttl_seconds=STATE_CACHE_TTL_SECONDS,
        builder=lambda: GardenStateService().snapshot(registry=registry, session=session),
    )


@router.get("/garden/charts")
def garden_charts(
    hours: int = 24,
    registry: EntityRegistry = Depends(get_registry),
    session: Session = Depends(get_db_session),
) -> dict:
    if hours < 1:
        hours = 1
    if hours > 168:
        hours = 168
    return get_dashboard_response_cache().get_or_set(
        ("garden", "charts", hours),
        ttl_seconds=HEAVY_CACHE_TTL_SECONDS,
        builder=lambda: GardenStateService().charts(registry=registry, session=session, hours=hours),
    )


@router.get("/garden/history")
def garden_history(
    hours: int = 24,
    session: Session = Depends(get_db_session),
) -> dict:
    if hours < 1:
        hours = 1
    if hours > 168:
        hours = 168
    return get_dashboard_response_cache().get_or_set(
        ("garden", "history", hours),
        ttl_seconds=HEAVY_CACHE_TTL_SECONDS,
        builder=lambda: GardenStateService().history(session=session, hours=hours),
    )


@router.get("/garden/config")
def garden_config(session: Session = Depends(get_db_session)) -> dict:
    return get_dashboard_response_cache().get_or_set(
        ("garden", "config"),
        ttl_seconds=HEAVY_CACHE_TTL_SECONDS,
        builder=lambda: ConfigService().get_garden_config(),
    )


@router.patch("/config/garden/climate")
def patch_climate_config(
    payload: ClimateConfigPatchPayload,
    _: bool = Depends(require_write_access),
    session: Session = Depends(get_db_session),
) -> dict:
    try:
        translated = GardenSettingsTranslator().climate_payload(payload.model_dump(exclude_none=True))
        result = ConfigService().update_garden_module(module="climate", payload=translated, session=session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    invalidate_dashboard_caches()
    return {"status": "ok", **result}


@router.patch("/config/garden/lighting")
def patch_lighting_config(
    payload: LightingConfigPatchPayload,
    _: bool = Depends(require_write_access),
    session: Session = Depends(get_db_session),
) -> dict:
    try:
        translated = GardenSettingsTranslator().lighting_payload(payload.model_dump(exclude_none=True))
        result = ConfigService().update_garden_module(module="light", payload=translated, session=session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    invalidate_dashboard_caches()
    return {"status": "ok", **result}


@router.patch("/config/garden/watering")
def patch_watering_config(
    payload: WateringConfigPatchPayload,
    _: bool = Depends(require_write_access),
    session: Session = Depends(get_db_session),
) -> dict:
    try:
        translated = GardenSettingsTranslator().watering_payload(payload.model_dump(exclude_none=True))
        result = ConfigService().update_garden_module(module="watering", payload=translated, session=session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    invalidate_dashboard_caches()
    return {"status": "ok", **result}


@router.patch("/config/garden/emergency")
def patch_emergency_config(
    payload: EmergencyConfigPatchPayload,
    _: bool = Depends(require_write_access),
    session: Session = Depends(get_db_session),
) -> dict:
    try:
        translated = GardenSettingsTranslator().emergency_payload(payload.model_dump(exclude_none=True))
        result = ConfigService().update_garden_module(module="emergency", payload=translated, session=session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    invalidate_dashboard_caches()
    return {"status": "ok", **result}


@router.patch("/config/garden/{module}/enabled")
def patch_garden_module_enabled(
    module: str,
    payload: GardenModuleEnabledPayload,
    _: bool = Depends(require_write_access),
    session: Session = Depends(get_db_session),
) -> dict:
    if module not in {"climate", "light", "watering", "emergency"}:
        raise HTTPException(status_code=404, detail=f"Unknown garden module: {module}")
    try:
        result = ConfigService().update_garden_module_enabled(
            module=module,
            enabled=payload.enabled,
            session=session,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    invalidate_dashboard_caches()
    return {"status": "ok", **result}


@router.post("/config/garden/reset")
def reset_garden_defaults(
    _: bool = Depends(require_write_access),
    session: Session = Depends(get_db_session),
) -> dict:
    try:
        result = ConfigService().reset_garden_defaults(session=session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    invalidate_dashboard_caches()
    return {"status": "ok", **result}


@router.post("/overrides/actuators/{actuator_id}")
def create_manual_override(
    actuator_id: str,
    payload: ManualOverridePayload,
    registry: EntityRegistry = Depends(get_registry),
    _: bool = Depends(require_write_access),
    session: Session = Depends(get_db_session),
) -> dict:
    registry.get_actuator(actuator_id)
    record = ManualOverrideService().create_override(
        session,
        actuator_id=actuator_id,
        mode=payload.mode,
        expires_after_minutes=payload.expires_after_minutes,
        pulse_seconds=payload.pulse_seconds,
        reason=payload.reason,
        source=payload.source,
    )
    session.commit()
    invalidate_dashboard_caches()
    return {
        "status": "ok",
        "override": {
            "id": record.id,
            "actuator_id": actuator_id,
            "mode": record.mode,
            "expires_at_utc": utc_isoformat(record.expires_at_utc),
        },
        "garden": GardenStateService().snapshot(registry=registry, session=session),
    }


@router.delete("/overrides/actuators/{actuator_id}")
def delete_manual_override(
    actuator_id: str,
    registry: EntityRegistry = Depends(get_registry),
    _: bool = Depends(require_write_access),
    session: Session = Depends(get_db_session),
) -> dict:
    registry.get_actuator(actuator_id)
    record = ManualOverrideService().cancel_override(session, actuator_id=actuator_id)
    session.commit()
    invalidate_dashboard_caches()
    return {
        "status": "ok",
        "cancelled": bool(record),
        "garden": GardenStateService().snapshot(registry=registry, session=session),
    }


@router.post("/garden/return-to-auto")
def return_all_to_auto(
    registry: EntityRegistry = Depends(get_registry),
    _: bool = Depends(require_write_access),
    session: Session = Depends(get_db_session),
) -> dict:
    cancelled = ManualOverrideService().cancel_all(session, source="return_to_auto")
    session.commit()
    invalidate_dashboard_caches()
    return {
        "status": "ok",
        "cancelled": cancelled,
        "garden": GardenStateService().snapshot(registry=registry, session=session),
    }


@router.post("/garden/safe-shutdown")
def safe_shutdown(
    registry: EntityRegistry = Depends(get_registry),
    _: bool = Depends(require_write_access),
    session: Session = Depends(get_db_session),
) -> dict:
    override_service = ManualOverrideService()
    override_service.create_override(session, actuator_id="exhaust_fan", mode="on", reason="safe_shutdown")
    override_service.create_override(session, actuator_id="warm_pads", mode="off", reason="safe_shutdown")
    override_service.create_override(session, actuator_id="lamps", mode="off", reason="safe_shutdown")
    override_service.create_override(session, actuator_id="water_pump", mode="off", reason="safe_shutdown")
    session.commit()
    invalidate_dashboard_caches()
    return {
        "status": "ok",
        "garden": GardenStateService().snapshot(registry=registry, session=session),
    }


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
            "ts_utc": utc_isoformat(latest_event.ts_utc),
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
    invalidate_dashboard_caches()
    return {
        **result,
        "garden": GardenStateService().snapshot(registry=registry, session=session),
    }
