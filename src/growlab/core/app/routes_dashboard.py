from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="src/growlab/core/templates")
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
):
    css_version = int(Path("src/growlab/core/static/css/app.css").stat().st_mtime)
    js_version = int(Path("src/growlab/core/static/js/dashboard.js").stat().st_mtime)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "title": "Garden Lab UI",
            "css_version": css_version,
            "js_version": js_version,
        },
    )
