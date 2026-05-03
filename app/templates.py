"""Single Jinja2 Templates instance shared across routers."""
from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
