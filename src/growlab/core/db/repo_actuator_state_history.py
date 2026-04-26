from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from growlab.core.db.models import ActuatorStateHistory
from growlab.shared.time import utc_now


def insert_actuator_state_history(
    session: Session,
    *,
    actuator_id: str,
    ts_utc: datetime,
    power: bool,
    source: str,
    quality: Optional[str] = None,
    observed_vs_commanded: Optional[bool] = None,
) -> ActuatorStateHistory:
    row = ActuatorStateHistory(
        actuator_id=actuator_id,
        ts_utc=ts_utc,
        power=power,
        source=source,
        quality=quality,
        observed_vs_commanded=observed_vs_commanded,
    )
    session.add(row)
    session.flush()
    return row


def get_latest_actuator_state_history(
    session: Session,
    *,
    actuator_id: str,
) -> Optional[ActuatorStateHistory]:
    stmt = (
        select(ActuatorStateHistory)
        .where(ActuatorStateHistory.actuator_id == actuator_id)
        .order_by(ActuatorStateHistory.ts_utc.desc(), ActuatorStateHistory.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def get_latest_actuator_state_history_batch(
    session: Session,
    *,
    actuator_ids: list[str],
) -> dict[str, ActuatorStateHistory]:
    if not actuator_ids:
        return {}
    ranked = (
        select(
            ActuatorStateHistory.id.label("id"),
            func.row_number()
            .over(
                partition_by=ActuatorStateHistory.actuator_id,
                order_by=(ActuatorStateHistory.ts_utc.desc(), ActuatorStateHistory.id.desc()),
            )
            .label("row_num"),
        )
        .where(ActuatorStateHistory.actuator_id.in_(actuator_ids))
        .subquery()
    )
    stmt = (
        select(ActuatorStateHistory)
        .join(ranked, ActuatorStateHistory.id == ranked.c.id)
        .where(ranked.c.row_num == 1)
    )
    return {row.actuator_id: row for row in session.execute(stmt).scalars().all()}


def list_actuator_state_history_window(
    session: Session,
    *,
    actuator_ids: list[str],
    hours: int,
) -> tuple[dict[str, Optional[ActuatorStateHistory]], dict[str, list[ActuatorStateHistory]], datetime, datetime]:
    window_end = utc_now()
    window_start = window_end - timedelta(hours=hours)
    if not actuator_ids:
        return {}, {}, window_start, window_end

    seed_ranked = (
        select(
            ActuatorStateHistory.id.label("id"),
            func.row_number()
            .over(
                partition_by=ActuatorStateHistory.actuator_id,
                order_by=(ActuatorStateHistory.ts_utc.desc(), ActuatorStateHistory.id.desc()),
            )
            .label("row_num"),
        )
        .where(
            ActuatorStateHistory.actuator_id.in_(actuator_ids),
            ActuatorStateHistory.ts_utc < window_start,
        )
        .subquery()
    )
    seed_stmt = (
        select(ActuatorStateHistory)
        .join(seed_ranked, ActuatorStateHistory.id == seed_ranked.c.id)
        .where(seed_ranked.c.row_num == 1)
    )
    seed_rows = {row.actuator_id: row for row in session.execute(seed_stmt).scalars().all()}

    conditions = [ActuatorStateHistory.actuator_id == actuator_id for actuator_id in actuator_ids]
    history_stmt = (
        select(ActuatorStateHistory)
        .where(
            or_(*conditions),
            ActuatorStateHistory.ts_utc >= window_start,
            ActuatorStateHistory.ts_utc <= window_end,
        )
        .order_by(ActuatorStateHistory.actuator_id, ActuatorStateHistory.ts_utc, ActuatorStateHistory.id)
    )
    history_rows: dict[str, list[ActuatorStateHistory]] = {actuator_id: [] for actuator_id in actuator_ids}
    for row in session.execute(history_stmt).scalars().all():
        history_rows.setdefault(row.actuator_id, []).append(row)

    seeds = {actuator_id: seed_rows.get(actuator_id) for actuator_id in actuator_ids}
    return seeds, history_rows, window_start, window_end
