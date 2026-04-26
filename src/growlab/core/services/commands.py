from __future__ import annotations

from sqlalchemy.orm import Session

from growlab.core.app.dependencies import get_actuator_state_service
from growlab.core.db.repo_actuator_state_history import get_latest_actuator_state_history, insert_actuator_state_history
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
        now = utc_now()
        insert_actuator_event(
            session,
            actuator_id=actuator_id,
            ts_utc=now,
            event_type="command",
            status="accepted" if result.get("accepted") else "error",
            payload=result,
        )
        power = result.get("state", {}).get("power")
        if result.get("accepted") and isinstance(power, bool):
            latest_state = get_latest_actuator_state_history(session, actuator_id=actuator_id)
            if latest_state is None or latest_state.power is not power:
                insert_actuator_state_history(
                    session,
                    actuator_id=actuator_id,
                    ts_utc=now,
                    power=power,
                    source="command_confirmed",
                    quality="confirmed",
                    observed_vs_commanded=True,
                )
        get_actuator_state_service().update_from_command_result(
            actuator_id=actuator_id,
            result=result,
        )
        return result
