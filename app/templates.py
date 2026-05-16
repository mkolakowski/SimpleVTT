"""Single Jinja2 Templates instance shared across routers."""
from __future__ import annotations

import re
from markupsafe import Markup, escape
from pathlib import Path

from fastapi.templating import Jinja2Templates

from .version import APP_VERSION, SCHEMA_VERSION
from .config import get_settings

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Expose version constants as Jinja globals so the base-template footer (and
# any other template that wants them) can reach them without each route
# passing them in its context dict.
templates.env.globals["APP_VERSION"] = APP_VERSION
templates.env.globals["SCHEMA_VERSION"] = SCHEMA_VERSION
templates.env.globals["APP_DEFAULT_THEME"] = get_settings().default_theme
templates.env.globals["DEMO_MODE"] = get_settings().demo_mode
templates.env.globals["DEMO_RESET_INTERVAL_MINUTES"] = get_settings().demo_reset_interval_minutes
templates.env.globals["DEMO_CREDENTIALS_VISIBLE"] = get_settings().demo_credentials_visible


def _bold_dice_in_breakdown(value: str) -> Markup:
    """Escape the breakdown string then bold individual die results inside [...]."""
    safe = str(escape(value))  # HTML-escape first
    def _bold_bracket(m: re.Match) -> str:
        inner = re.sub(r'(\d+)', r'<strong>\1</strong>', m.group(1))
        return f'[{inner}]'
    return Markup(re.sub(r'\[([^\]]*)\]', _bold_bracket, safe))


templates.env.filters['bold_dice'] = _bold_dice_in_breakdown
