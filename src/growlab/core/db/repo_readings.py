from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Union

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from growlab.core.db.models import SensorReading
from growlab.shared.time import utc_now


def insert_sensor_metrics(
    session: Session,
    *,
    sensor_id: str,
    ts_utc: datetime,
    metrics: dict[str, Union[float, int, str, bool, None]],
    source_kind: str,
    source_id: str,
) -> None:
    for metric, value in metrics.items():
        reading = SensorReading(
            sensor_id=sensor_id,
            ts_utc=ts_utc,
            metric=metric,
            value_num=float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None,
            value_text=None if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value),
            quality=None,
            source_kind=source_kind,
            source_id=source_id,
        )
        session.add(reading)


def get_latest_sensor_metrics(
    session: Session,
    *,
    sensor_id: str,
) -> dict[str, Optional[Union[float, str]]]:
    return get_latest_sensor_metrics_batch(session, sensor_ids=[sensor_id]).get(sensor_id, {})


def get_latest_sensor_metrics_batch(
    session: Session,
    *,
    sensor_ids: list[str],
) -> dict[str, dict[str, Optional[Union[float, str]]]]:
    if not sensor_ids:
        return {}

    latest_ts = (
        select(
            SensorReading.sensor_id.label("sensor_id"),
            func.max(SensorReading.ts_utc).label("max_ts_utc"),
        )
        .where(SensorReading.sensor_id.in_(sensor_ids))
        .group_by(SensorReading.sensor_id)
        .subquery()
    )
    stmt = (
        select(SensorReading)
        .join(
            latest_ts,
            and_(
                SensorReading.sensor_id == latest_ts.c.sensor_id,
                SensorReading.ts_utc == latest_ts.c.max_ts_utc,
            ),
        )
        .order_by(SensorReading.sensor_id, SensorReading.metric)
    )
    rows = session.execute(stmt).scalars().all()
    data = {sensor_id: {} for sensor_id in sensor_ids}
    for row in rows:
        data.setdefault(row.sensor_id, {})[row.metric] = (
            row.value_num if row.value_num is not None else row.value_text
        )
    return data


def get_sensor_history(
    session: Session,
    *,
    sensor_id: str,
    metric: str,
    hours: int = 24,
    limit: int = 2000,
) -> list[SensorReading]:
    since = utc_now() - timedelta(hours=hours)
    stmt = (
        select(SensorReading)
        .where(
            SensorReading.sensor_id == sensor_id,
            SensorReading.metric == metric,
            SensorReading.ts_utc >= since,
        )
        .order_by(desc(SensorReading.ts_utc), SensorReading.id.desc())
        .limit(limit)
    )
    return list(reversed(session.execute(stmt).scalars().all()))


def get_sensor_history_batch(
    session: Session,
    *,
    refs: list[tuple[str, str]],
    hours: int = 24,
    limit_per_metric: int = 2000,
) -> dict[tuple[str, str], list[SensorReading]]:
    if not refs:
        return {}

    since = utc_now() - timedelta(hours=hours)
    conditions = [
        and_(SensorReading.sensor_id == sensor_id, SensorReading.metric == metric)
        for sensor_id, metric in refs
    ]
    ranked = (
        select(
            SensorReading.id.label("id"),
            func.row_number()
            .over(
                partition_by=(SensorReading.sensor_id, SensorReading.metric),
                order_by=(SensorReading.ts_utc.desc(), SensorReading.id.desc()),
            )
            .label("row_num"),
        )
        .where(
            SensorReading.ts_utc >= since,
            or_(*conditions),
        )
        .subquery()
    )
    stmt = (
        select(SensorReading)
        .join(ranked, SensorReading.id == ranked.c.id)
        .where(ranked.c.row_num <= limit_per_metric)
        .order_by(SensorReading.sensor_id, SensorReading.metric, SensorReading.ts_utc, SensorReading.id)
    )
    grouped: dict[tuple[str, str], list[SensorReading]] = {ref: [] for ref in refs}
    for row in session.execute(stmt).scalars().all():
        grouped.setdefault((row.sensor_id, row.metric), []).append(row)
    return grouped
