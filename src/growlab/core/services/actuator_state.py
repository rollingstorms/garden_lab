from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Optional

from sqlalchemy.orm import Session

from growlab.core.config.registry import EntityRegistry
from growlab.core.db.repo_actuator_state_history import get_latest_actuator_state_history, insert_actuator_state_history
from growlab.core.db.repo_events import get_latest_actuator_event
from growlab.core.drivers.registry import load_actuator_driver
from growlab.shared.time import utc_now


@dataclass
class ActuatorStateSnapshot:
    actuator_id: str
    power: Optional[bool]
    state_status: str
    state_source: str
    last_seen_at: Optional[str] = None
    error: Optional[str] = None
    driver_state: Optional[dict[str, Any]] = None


class ActuatorStateService:
    def __init__(self) -> None:
        self._lock = RLock()
        self._cache: dict[str, ActuatorStateSnapshot] = {}

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def get_state(
        self,
        *,
        registry: EntityRegistry,
        session: Session,
        actuator_id: str,
    ) -> ActuatorStateSnapshot:
        with self._lock:
            cached = self._cache.get(actuator_id)
        if cached is not None:
            return cached
        return self._fallback_state(session=session, actuator_id=actuator_id)

    def get_states(
        self,
        *,
        registry: EntityRegistry,
        session: Session,
    ) -> dict[str, ActuatorStateSnapshot]:
        return {
            actuator_id: self.get_state(
                registry=registry,
                session=session,
                actuator_id=actuator_id,
            )
            for actuator_id in registry.config.actuators
        }

    def refresh_actuator(
        self,
        *,
        registry: EntityRegistry,
        session: Session,
        actuator_id: str,
        history_source: str = "live_refresh",
    ) -> ActuatorStateSnapshot:
        actuator = registry.get_actuator(actuator_id)
        driver = load_actuator_driver(registry.config, actuator.driver)
        driver.setup(actuator.config)

        result = driver.get_state()
        now = utc_now()
        now_iso = now.isoformat()
        previous = self._cache.get(actuator_id)
        power = result.get("state", {}).get("power")
        if result.get("status") == "ok" and isinstance(power, bool):
            self._persist_state_if_changed(
                session=session,
                actuator_id=actuator_id,
                ts_utc=now,
                power=power,
                source=history_source,
                quality="observed",
                observed_vs_commanded=None,
            )
            snapshot = ActuatorStateSnapshot(
                actuator_id=actuator_id,
                power=power,
                state_status="ok",
                state_source="live",
                last_seen_at=now_iso,
                error=None,
                driver_state=result,
            )
        elif previous is not None:
            snapshot = ActuatorStateSnapshot(
                actuator_id=actuator_id,
                power=previous.power,
                state_status="stale",
                state_source="live",
                last_seen_at=previous.last_seen_at,
                error=result.get("error"),
                driver_state=result,
            )
        else:
            fallback = self._fallback_state(session=session, actuator_id=actuator_id)
            snapshot = ActuatorStateSnapshot(
                actuator_id=actuator_id,
                power=fallback.power,
                state_status="fallback" if fallback.state_source in {"fallback_event", "history"} else "unknown",
                state_source=fallback.state_source,
                last_seen_at=fallback.last_seen_at,
                error=result.get("error"),
                driver_state=result,
            )

        with self._lock:
            self._cache[actuator_id] = snapshot
        return snapshot

    def refresh_all(
        self,
        *,
        registry: EntityRegistry,
        session: Session,
    ) -> dict[str, ActuatorStateSnapshot]:
        return {
            actuator_id: self.refresh_actuator(
                registry=registry,
                session=session,
                actuator_id=actuator_id,
                history_source="live_poll",
            )
            for actuator_id in registry.config.actuators
        }

    def update_from_command_result(
        self,
        *,
        actuator_id: str,
        result: dict[str, Any],
    ) -> None:
        power = result.get("state", {}).get("power")
        if not result.get("accepted") or not isinstance(power, bool):
            return
        snapshot = ActuatorStateSnapshot(
            actuator_id=actuator_id,
            power=power,
            state_status="ok",
            state_source="live",
            last_seen_at=utc_now().isoformat(),
            error=None,
            driver_state=result,
        )
        with self._lock:
            self._cache[actuator_id] = snapshot

    def _fallback_state(
        self,
        *,
        session: Session,
        actuator_id: str,
    ) -> ActuatorStateSnapshot:
        latest_history = get_latest_actuator_state_history(session, actuator_id=actuator_id)
        if latest_history is not None:
            return ActuatorStateSnapshot(
                actuator_id=actuator_id,
                power=latest_history.power,
                state_status="fallback",
                state_source="history",
                last_seen_at=latest_history.ts_utc.isoformat(),
            )
        latest_event = get_latest_actuator_event(session, actuator_id=actuator_id)
        power = None
        ts_utc = None
        if latest_event and isinstance(latest_event.payload_json.get("command"), dict):
            command = latest_event.payload_json["command"]
            if isinstance(command.get("power"), bool):
                power = command["power"]
                ts_utc = latest_event.ts_utc.isoformat()
        if isinstance(power, bool):
            return ActuatorStateSnapshot(
                actuator_id=actuator_id,
                power=power,
                state_status="fallback",
                state_source="fallback_event",
                last_seen_at=ts_utc,
            )
        return ActuatorStateSnapshot(
            actuator_id=actuator_id,
            power=None,
            state_status="unknown",
            state_source="unknown",
            last_seen_at=None,
        )

    def _persist_state_if_changed(
        self,
        *,
        session: Session,
        actuator_id: str,
        ts_utc,
        power: bool,
        source: str,
        quality: Optional[str],
        observed_vs_commanded: Optional[bool],
    ) -> None:
        latest_history = get_latest_actuator_state_history(session, actuator_id=actuator_id)
        if latest_history is not None and latest_history.power is power:
            return
        insert_actuator_state_history(
            session,
            actuator_id=actuator_id,
            ts_utc=ts_utc,
            power=power,
            source=source,
            quality=quality,
            observed_vs_commanded=observed_vs_commanded,
        )
