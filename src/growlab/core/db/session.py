from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from growlab.core.config.models import AppConfig


def build_engine(app_config: AppConfig):
    return create_engine(app_config.database_url, future=True)


def build_session_factory(app_config: AppConfig):
    engine = build_engine(app_config)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
