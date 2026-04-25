from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="src/growlab/core/templates")
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "title": "Garden Lab UI",
        },
    )
