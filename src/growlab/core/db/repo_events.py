from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from growlab.core.db.models import ActuatorEvent, AutomationEvent, CollectorEvent


def insert_collector_heartbeat(
    session: Session,
    *,
    collector_id: str,
    ts_utc: datetime,
    status: str,
    payload: dict,
) -> None:
    session.add(
        CollectorEvent(
            collector_id=collector_id,
            ts_utc=ts_utc,
            event_type="heartbeat",
            status=status,
            payload_json=payload,
        )
    )


def insert_actuator_event(
    session: Session,
    *,
    actuator_id: str,
    ts_utc: datetime,
    event_type: str,
    status: str,
    payload: dict,
) -> None:
    session.add(
        ActuatorEvent(
            actuator_id=actuator_id,
            ts_utc=ts_utc,
            event_type=event_type,
            status=status,
            payload_json=payload,
        )
    )


def get_latest_actuator_event(session: Session, *, actuator_id: str) -> Optional[ActuatorEvent]:
    stmt = (
        select(ActuatorEvent)
        .where(ActuatorEvent.actuator_id == actuator_id)
        .order_by(desc(ActuatorEvent.ts_utc), ActuatorEvent.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def insert_automation_event(
    session: Session,
    *,
    automation_id: str,
    ts_utc: datetime,
    decision: str,
    reason: str,
    payload: dict,
) -> None:
    session.add(
        AutomationEvent(
            automation_id=automation_id,
            ts_utc=ts_utc,
            decision=decision,
            reason=reason,
            payload_json=payload,
        )
    )


def get_latest_automation_event(session: Session, *, automation_id: str) -> Optional[AutomationEvent]:
    stmt = (
        select(AutomationEvent)
        .where(AutomationEvent.automation_id == automation_id)
        .order_by(desc(AutomationEvent.ts_utc), AutomationEvent.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()
