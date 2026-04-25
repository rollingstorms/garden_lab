from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from growlab.core.config.loader import load_config
from growlab.core.config.registry import EntityRegistry
from growlab.core.db.session import build_engine, build_session_factory


@lru_cache(maxsize=1)
def get_config():
    base = Path(os.environ.get("GROWLAB_CONFIG_BASE", "config/base.yaml"))
    local = Path(os.environ.get("GROWLAB_CONFIG_LOCAL", "config/local.yaml"))
    return load_config(base, local)


def get_config_paths() -> tuple[Path, Path]:
    base = Path(os.environ.get("GROWLAB_CONFIG_BASE", "config/base.yaml"))
    local = Path(os.environ.get("GROWLAB_CONFIG_LOCAL", "config/local.yaml"))
    return base, local


@lru_cache(maxsize=1)
def get_registry() -> EntityRegistry:
    return EntityRegistry(config=get_config())


@lru_cache(maxsize=1)
def get_engine():
    return build_engine(get_config().app)


@lru_cache(maxsize=1)
def get_session_factory():
    return build_session_factory(get_config().app)


def get_db_session():
    session_factory = get_session_factory()
    session: Session = session_factory()
    try:
        yield session
    finally:
        session.close()


def reset_runtime_caches() -> None:
    get_config.cache_clear()
    get_registry.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
