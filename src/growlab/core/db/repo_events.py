from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from growlab.core.db.models import (
    ActuatorEvent,
    AutomationEvent,
    CollectorEvent,
    SystemEvent,
)
from growlab.shared.time import utc_now


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


def list_recent_actuator_events(
    session: Session,
    *,
    actuator_id: Optional[str] = None,
    limit: int = 100,
) -> list[ActuatorEvent]:
    stmt = select(ActuatorEvent).order_by(desc(ActuatorEvent.ts_utc), ActuatorEvent.id.desc()).limit(limit)
    if actuator_id:
        stmt = stmt.where(ActuatorEvent.actuator_id == actuator_id)
    return list(reversed(session.execute(stmt).scalars().all()))


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


def list_recent_automation_events(
    session: Session,
    *,
    automation_id: Optional[str] = None,
    limit: int = 100,
) -> list[AutomationEvent]:
    stmt = (
        select(AutomationEvent)
        .order_by(desc(AutomationEvent.ts_utc), AutomationEvent.id.desc())
        .limit(limit)
    )
    if automation_id:
        stmt = stmt.where(AutomationEvent.automation_id == automation_id)
    return list(reversed(session.execute(stmt).scalars().all()))


def insert_system_event(
    session: Session,
    *,
    category: str,
    event_type: str,
    message: str,
    payload: dict,
    entity_id: Optional[str] = None,
    status: str = "ok",
    ts_utc: Optional[datetime] = None,
) -> None:
    session.add(
        SystemEvent(
            category=category,
            entity_id=entity_id,
            event_type=event_type,
            status=status,
            message=message,
            payload_json=payload,
            ts_utc=ts_utc or utc_now(),
        )
    )


def list_recent_system_events(
    session: Session,
    *,
    category: Optional[str] = None,
    limit: int = 100,
) -> list[SystemEvent]:
    stmt = select(SystemEvent).order_by(desc(SystemEvent.ts_utc), SystemEvent.id.desc()).limit(limit)
    if category:
        stmt = stmt.where(SystemEvent.category == category)
    return list(reversed(session.execute(stmt).scalars().all()))
