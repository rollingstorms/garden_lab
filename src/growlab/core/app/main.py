from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from growlab.core.app.dependencies import get_config
from growlab.core.app.routes_api import router as api_router
from growlab.core.app.routes_dashboard import router as dashboard_router
from growlab.core.db.models import Base
from growlab.core.db.session import build_engine, ensure_sqlite_runtime_indexes
from growlab.core.services.scheduler import AutomationScheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AutomationScheduler(app_config=get_config().app)
    scheduler.start()
    app.state.automation_scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown()


def create_app() -> FastAPI:
    config = get_config()
    engine = build_engine(config.app)
    Base.metadata.create_all(engine)
    ensure_sqlite_runtime_indexes(engine)

    app = FastAPI(title="garden_lab core", lifespan=lifespan)
    app.include_router(api_router)
    app.include_router(dashboard_router)
    app.mount("/static", StaticFiles(directory="src/growlab/core/static"), name="static")
    return app


app = create_app()
