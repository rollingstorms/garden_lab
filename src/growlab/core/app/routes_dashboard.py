from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

from growlab.core.app.dependencies import get_db_session, get_registry
from growlab.core.config.registry import EntityRegistry
from growlab.core.services.dashboard import DashboardService

templates = Jinja2Templates(directory="src/growlab/core/templates")
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    registry: EntityRegistry = Depends(get_registry),
    session: Session = Depends(get_db_session),
):
    dashboard_view = DashboardService().build_dashboard_view(registry=registry, session=session)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "title": dashboard_view["title"],
            "panels": dashboard_view["panels"],
        },
    )
