"""Single Jinja2 Templates instance shared across routers."""
from __future__ import annotations

import re
from markupsafe import Markup, escape
from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _bold_dice_in_breakdown(value: str) -> Markup:
    """Escape the breakdown string then bold individual die results inside [...]."""
    safe = str(escape(value))  # HTML-escape first
    def _bold_bracket(m: re.Match) -> str:
        inner = re.sub(r'(\d+)', r'<strong>\1</strong>', m.group(1))
        return f'[{inner}]'
    return Markup(re.sub(r'\[([^\]]*)\]', _bold_bracket, safe))


templates.env.filters['bold_dice'] = _bold_dice_in_breakdown
