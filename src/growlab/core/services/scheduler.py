from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from growlab.core.app.dependencies import (
    get_actuator_state_service,
    get_dashboard_response_cache,
    get_registry,
    get_session_factory,
)
from growlab.core.config.models import AppConfig
from growlab.core.services.automation import AutomationService

logger = logging.getLogger(__name__)


class AutomationScheduler:
    def __init__(self, *, app_config: AppConfig) -> None:
        self.app_config = app_config
        self.scheduler = BackgroundScheduler(timezone=app_config.timezone)
        self.automation_service = AutomationService()

    def start(self) -> None:
        interval_seconds = max(1, int(self.app_config.automation_interval_seconds))
        now = datetime.now(self.scheduler.timezone)
        self.scheduler.add_job(
            self.refresh_actuator_state_cache,
            trigger="interval",
            seconds=interval_seconds,
            id="actuator-state-refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=now + timedelta(seconds=max(1, interval_seconds // 2)),
        )
        self.scheduler.add_job(
            self.run_cycle,
            trigger="interval",
            seconds=interval_seconds,
            id="automation-cycle",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=now + timedelta(seconds=interval_seconds),
        )
        self.scheduler.start()
        logger.info(
            "Started automation scheduler with %s second interval",
            interval_seconds,
        )

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def run_cycle(self) -> None:
        session_factory = get_session_factory()
        session = session_factory()
        try:
            result = self.automation_service.run_cycle(
                registry=get_registry(),
                session=session,
            )
            session.commit()
            get_dashboard_response_cache().invalidate_prefix(("garden",))
            logger.info("Automation cycle finished: %s", result)
        except Exception:
            session.rollback()
            logger.exception("Automation cycle failed")
        finally:
            session.close()

    def refresh_actuator_state_cache(self) -> None:
        session_factory = get_session_factory()
        session = session_factory()
        try:
            get_actuator_state_service().refresh_all(
                registry=get_registry(),
                session=session,
            )
            session.commit()
            get_dashboard_response_cache().invalidate_prefix(("garden",))
        except Exception:
            session.rollback()
            logger.exception("Actuator state refresh failed")
        finally:
            session.close()
