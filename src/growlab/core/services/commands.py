from __future__ import annotations

from sqlalchemy.orm import Session

from growlab.core.app.dependencies import get_actuator_state_service
from growlab.core.config.registry import EntityRegistry
from growlab.core.db.repo_events import insert_actuator_event
from growlab.core.drivers.registry import load_actuator_driver
from growlab.core.schemas.api import ActuatorCommandPayload
from growlab.shared.time import utc_now


class CommandService:
    def issue_command(
        self,
        *,
        registry: EntityRegistry,
        session: Session,
        actuator_id: str,
        payload: ActuatorCommandPayload,
    ) -> dict:
        actuator = registry.get_actuator(actuator_id)
        driver = load_actuator_driver(registry.config, actuator.driver)
        driver.setup(actuator.config)
        driver_result = driver.apply(payload.command)
        result = {
            "actuator_id": actuator_id,
            "driver": actuator.driver,
            **driver_result,
        }
        insert_actuator_event(
            session,
            actuator_id=actuator_id,
            ts_utc=utc_now(),
            event_type="command",
            status="accepted" if result.get("accepted") else "error",
            payload=result,
        )
        get_actuator_state_service().update_from_command_result(
            actuator_id=actuator_id,
            result=result,
        )
        return result
