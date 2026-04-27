from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, timezone

from sqlalchemy.orm import Session

from growlab.core.db.models import ManualOverride
from growlab.core.db.repo_events import insert_actuator_event
from growlab.core.db.repo_overrides import (
    get_active_manual_override,
    insert_manual_override,
    list_active_manual_overrides,
    list_manual_overrides,
    update_manual_override_status,
)
from growlab.shared.time import utc_isoformat, utc_now

DEFAULT_OVERRIDE_MINUTES = {
    "exhaust_fan": 30,
    "warm_pads": 30,
    "lamps": 30,
    "water_pump": 5,
}


@dataclass
class OverrideCommand:
    actuator_id: str
    power: bool
    mode: str
    reason: str
    source: str


class ManualOverrideService:
    def create_override(
        self,
        session: Session,
        *,
        actuator_id: str,
        mode: str,
        expires_after_minutes: int | None = None,
        pulse_seconds: int | None = None,
        reason: str | None = None,
        source: str = "dashboard",
    ) -> ManualOverride:
        now = utc_now()
        active = get_active_manual_override(session, actuator_id=actuator_id)
        if active:
            update_manual_override_status(session, override=active, status="cancelled", updated_at_utc=now)

        if mode == "pulse":
            duration_seconds = pulse_seconds or 5
            expires_at_utc = now + timedelta(seconds=duration_seconds)
        else:
            minutes = expires_after_minutes or DEFAULT_OVERRIDE_MINUTES.get(actuator_id, 30)
            expires_at_utc = now + timedelta(minutes=minutes)

        record = insert_manual_override(
            session,
            actuator_id=actuator_id,
            mode=mode,
            expires_at_utc=expires_at_utc,
            pulse_seconds=pulse_seconds,
            reason=reason,
            source=source,
        )
        insert_actuator_event(
            session,
            actuator_id=actuator_id,
            ts_utc=now,
            event_type="manual_override_created",
            status="accepted",
            payload={
                "override_id": record.id,
                "mode": mode,
                "pulse_seconds": pulse_seconds,
                "expires_at_utc": utc_isoformat(expires_at_utc),
                "reason": reason,
                "source": source,
            },
        )
        return record

    def cancel_override(self, session: Session, *, actuator_id: str, source: str = "dashboard") -> ManualOverride | None:
        now = utc_now()
        active = get_active_manual_override(session, actuator_id=actuator_id)
        if active is None:
            return None
        update_manual_override_status(session, override=active, status="cancelled", updated_at_utc=now)
        insert_actuator_event(
            session,
            actuator_id=actuator_id,
            ts_utc=now,
            event_type="manual_override_cancelled",
            status="accepted",
            payload={"override_id": active.id, "source": source},
        )
        return active

    def cancel_all(self, session: Session, *, source: str = "dashboard") -> list[str]:
        cancelled: list[str] = []
        for override in list_active_manual_overrides(session):
            update_manual_override_status(session, override=override, status="cancelled", updated_at_utc=utc_now())
            insert_actuator_event(
                session,
                actuator_id=override.actuator_id,
                ts_utc=utc_now(),
                event_type="manual_override_cancelled",
                status="accepted",
                payload={"override_id": override.id, "source": source},
            )
            cancelled.append(override.actuator_id)
        return cancelled

    def cleanup_expired(self, session: Session) -> list[ManualOverride]:
        now = utc_now()
        expired: list[ManualOverride] = []
        for override in list_manual_overrides(session, status="active", limit=500):
            expires_at = override.expires_at_utc
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at > now:
                continue
            status = "completed" if override.mode == "pulse" else "expired"
            update_manual_override_status(session, override=override, status=status, updated_at_utc=now)
            insert_actuator_event(
                session,
                actuator_id=override.actuator_id,
                ts_utc=now,
                event_type=f"manual_override_{status}",
                status="accepted",
                payload={"override_id": override.id, "mode": override.mode},
            )
            expired.append(override)
        return expired

    def active_commands(self, session: Session) -> list[OverrideCommand]:
        self.cleanup_expired(session)
        commands: list[OverrideCommand] = []
        for override in list_active_manual_overrides(session):
            commands.append(
                OverrideCommand(
                    actuator_id=override.actuator_id,
                    power=override.mode in {"on", "pulse"},
                    mode=override.mode,
                    reason=self.describe_override(override),
                    source="manual_override",
                )
            )
        return commands

    def recent_history(self, session: Session, *, limit: int = 50) -> list[ManualOverride]:
        return list_manual_overrides(session, limit=limit)

    def describe_override(self, override: ManualOverride) -> str:
        if override.mode == "pulse":
            seconds = override.pulse_seconds or 5
            return f"{override.actuator_id} pulsed for {seconds}s"
        if override.mode == "on":
            return f"{override.actuator_id} manual override ON"
        return f"{override.actuator_id} manual override OFF"
