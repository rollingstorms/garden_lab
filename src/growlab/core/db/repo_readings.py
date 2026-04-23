from __future__ import annotations

from datetime import datetime
from typing import Optional, Union

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from growlab.core.db.models import SensorReading


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
    stmt = (
        select(SensorReading)
        .where(SensorReading.sensor_id == sensor_id)
        .order_by(desc(SensorReading.ts_utc), SensorReading.id.desc())
    )
    rows = session.execute(stmt).scalars().all()
    latest_ts = None
    latest: dict[str, Optional[Union[float, str]]] = {}
    for row in rows:
        if latest_ts is None:
            latest_ts = row.ts_utc
        if row.ts_utc != latest_ts:
            break
        latest[row.metric] = row.value_num if row.value_num is not None else row.value_text
    return latest


def get_sensor_history(
    session: Session,
    *,
    sensor_id: str,
    metric: str,
    limit: int = 200,
) -> list[SensorReading]:
    stmt = (
        select(SensorReading)
        .where(SensorReading.sensor_id == sensor_id, SensorReading.metric == metric)
        .order_by(desc(SensorReading.ts_utc), SensorReading.id.desc())
        .limit(limit)
    )
    return list(reversed(session.execute(stmt).scalars().all()))
