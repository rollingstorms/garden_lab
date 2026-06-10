from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from growlab.core.config.models import AppConfig


def build_engine(app_config: AppConfig):
    connect_args = {}
    if app_config.database_url.startswith("sqlite"):
        connect_args["timeout"] = 30
    engine = create_engine(app_config.database_url, connect_args=connect_args, future=True)
    if app_config.database_url.startswith("sqlite"):
        _configure_sqlite_engine(engine)
    return engine


def _configure_sqlite_engine(engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def build_session_factory(app_config: AppConfig):
    engine = build_engine(app_config)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
