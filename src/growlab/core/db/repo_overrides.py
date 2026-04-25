from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from growlab.core.db.models import ManualOverride
from growlab.shared.time import utc_now


def insert_manual_override(
    session: Session,
    *,
    actuator_id: str,
    mode: str,
    expires_at_utc: datetime,
    pulse_seconds: Optional[int] = None,
    reason: Optional[str] = None,
    source: str = "dashboard",
    status: str = "active",
) -> ManualOverride:
    record = ManualOverride(
        actuator_id=actuator_id,
        mode=mode,
        pulse_seconds=pulse_seconds,
        expires_at_utc=expires_at_utc,
        reason=reason,
        source=source,
        status=status,
    )
    session.add(record)
    session.flush()
    return record


def list_manual_overrides(
    session: Session,
    *,
    actuator_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> list[ManualOverride]:
    stmt = (
        select(ManualOverride)
        .order_by(desc(ManualOverride.created_at_utc), ManualOverride.id.desc())
        .limit(limit)
    )
    if actuator_id:
        stmt = stmt.where(ManualOverride.actuator_id == actuator_id)
    if status:
        stmt = stmt.where(ManualOverride.status == status)
    return list(reversed(session.execute(stmt).scalars().all()))


def get_active_manual_override(
    session: Session,
    *,
    actuator_id: str,
) -> Optional[ManualOverride]:
    stmt = (
        select(ManualOverride)
        .where(
            ManualOverride.actuator_id == actuator_id,
            ManualOverride.status == "active",
            ManualOverride.expires_at_utc > utc_now(),
        )
        .order_by(desc(ManualOverride.created_at_utc), ManualOverride.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def list_active_manual_overrides(session: Session) -> list[ManualOverride]:
    stmt = (
        select(ManualOverride)
        .where(ManualOverride.status == "active", ManualOverride.expires_at_utc > utc_now())
        .order_by(desc(ManualOverride.created_at_utc), ManualOverride.id.desc())
    )
    return list(session.execute(stmt).scalars().all())


def update_manual_override_status(
    session: Session,
    *,
    override: ManualOverride,
    status: str,
    updated_at_utc: datetime,
) -> ManualOverride:
    override.status = status
    override.updated_at_utc = updated_at_utc
    session.add(override)
    session.flush()
    return override
