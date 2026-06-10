from __future__ import annotations

from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from growlab.shared.time import utc_now


class Base(DeclarativeBase):
    pass


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (
        Index("ix_sensor_readings_sensor_metric_ts", "sensor_id", "metric", "ts_utc"),
        Index("ix_sensor_readings_sensor_ts", "sensor_id", "ts_utc"),
    )

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
    __table_args__ = (
        Index("ix_actuator_events_actuator_ts", "actuator_id", "ts_utc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actuator_id: Mapped[str] = mapped_column(String(120), index=True)
    ts_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ActuatorStateHistory(Base):
    __tablename__ = "actuator_state_history"
    __table_args__ = (
        Index("ix_actuator_state_history_actuator_ts", "actuator_id", "ts_utc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actuator_id: Mapped[str] = mapped_column(String(120), index=True)
    ts_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    power: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(64), index=True)
    quality: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    observed_vs_commanded: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)


class AutomationEvent(Base):
    __tablename__ = "automation_events"
    __table_args__ = (
        Index("ix_automation_events_automation_ts", "automation_id", "ts_utc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    automation_id: Mapped[str] = mapped_column(String(120), index=True)
    ts_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    decision: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(255))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ManualOverride(Base):
    __tablename__ = "manual_overrides"
    __table_args__ = (
        Index("ix_manual_overrides_status_expires", "status", "expires_at_utc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actuator_id: Mapped[str] = mapped_column(String(120), index=True)
    mode: Mapped[str] = mapped_column(String(32), index=True)
    pulse_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="dashboard")
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    expires_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), index=True)
    created_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SystemEvent(Base):
    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(120), index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(64), default="ok")
    message: Mapped[str] = mapped_column(String(255))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    ts_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
