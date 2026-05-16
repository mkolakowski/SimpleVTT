"""Single Jinja2 Templates instance shared across routers."""
from __future__ import annotations

import re
from markupsafe import Markup, escape
from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import ChainableUndefined

from .version import APP_VERSION, SCHEMA_VERSION
from .config import get_settings

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
# ChainableUndefined lets ``{{ user.foo or '' }}`` evaluate to ``''`` when
# ``user`` itself is undefined — the pattern every template in this codebase
# already assumes for logged-out pages. Default Jinja Undefined raises
# UndefinedError on attribute access, breaking the login / register pages.
# Starlette 1.0's Jinja2Templates dropped the kwarg passthrough, so we
# set ``undefined`` on the env after construction.
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
templates.env.undefined = ChainableUndefined

# Expose version constants as Jinja globals so the base-template footer (and
# any other template that wants them) can reach them without each route
# passing them in its context dict.
templates.env.globals["APP_VERSION"] = APP_VERSION
templates.env.globals["SCHEMA_VERSION"] = SCHEMA_VERSION
templates.env.globals["APP_DEFAULT_THEME"] = get_settings().default_theme
templates.env.globals["DEMO_MODE"] = get_settings().demo_mode
templates.env.globals["DEMO_RESET_INTERVAL_MINUTES"] = get_settings().demo_reset_interval_minutes
templates.env.globals["DEMO_CREDENTIALS_VISIBLE"] = get_settings().demo_credentials_visible


# Starlette 1.0 (2026) removed the legacy ``TemplateResponse(name, context)``
# signature in favor of ``TemplateResponse(request, name, context)``. This
# project's 21 call sites all use the legacy form. Rather than touch every
# call site (and risk missing one), wrap the method here so both signatures
# work — detected by whether the first positional arg is a str. Drop this
# shim when the codebase has been swept to the new signature.
_starlette_tr = templates.TemplateResponse

def _compat_template_response(*args, **kwargs):
    if args and isinstance(args[0], str):
        # Legacy: (name, context, ...). Context dict must include
        # ``request``; pull it out and forward to the new signature.
        name = args[0]
        context = args[1] if len(args) > 1 else kwargs.pop("context", None) or {}
        if not isinstance(context, dict):
            raise TypeError("legacy TemplateResponse: context must be a dict")
        request = context.get("request")
        if request is None:
            raise RuntimeError(
                "legacy TemplateResponse: context['request'] is required"
            )
        return _starlette_tr(request, name, context, *args[2:], **kwargs)
    return _starlette_tr(*args, **kwargs)

templates.TemplateResponse = _compat_template_response  # type: ignore[assignment]


def _bold_dice_in_breakdown(value: str) -> Markup:
    """Escape the breakdown string then bold individual die results inside [...]."""
    safe = str(escape(value))  # HTML-escape first
    def _bold_bracket(m: re.Match) -> str:
        inner = re.sub(r'(\d+)', r'<strong>\1</strong>', m.group(1))
        return f'[{inner}]'
    return Markup(re.sub(r'\[([^\]]*)\]', _bold_bracket, safe))


templates.env.filters['bold_dice'] = _bold_dice_in_breakdown
