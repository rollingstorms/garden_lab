from __future__ import annotations

from typing import Optional

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from growlab.shared.time import utc_now


class Base(DeclarativeBase):
    pass


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sensor_id: Mapped[str] = mapped_column(String(120), index=True)
    ts_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), index=True)
    metric: Mapped[str] = mapped_column(String(120), index=True)
    value_num: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quality: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[str] = mapped_column(String(120), index=True)


class CollectorEvent(Base):
    __tablename__ = "collector_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collector_id: Mapped[str] = mapped_column(String(120), index=True)
    ts_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)
    event_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ActuatorEvent(Base):
    __tablename__ = "actuator_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actuator_id: Mapped[str] = mapped_column(String(120), index=True)
    ts_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)


class AutomationEvent(Base):
    __tablename__ = "automation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    automation_id: Mapped[str] = mapped_column(String(120), index=True)
    ts_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    decision: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(255))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
