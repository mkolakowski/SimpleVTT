"""SimpleVTT Admin Center — standalone ASGI app.

Runs on its own port (default 8015) from the same Docker image as the
main app. Read-only operator dashboard over the data SimpleVTT
collects: the audit log + derived traffic stats (this module's
panels), with fail2ban ban state + a DB data-inventory added in
later phases.

Launch: ``uvicorn app.admin_center.main:app --host 0.0.0.0 --port 8015``
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from ..version import APP_VERSION
from . import audit_parse, fail2ban, inventory, stats
from .basic_auth import header_authorizes, is_default_password

log = logging.getLogger("simplevtt.admin_center")

# Same default as the main app's RotatingFileHandler. The admin-center
# service mounts the audit_logs volume read-only at this path.
AUDIT_LOG_PATH = os.environ.get(
    "AUDIT_LOG_PATH", "/var/log/simplevtt/audit.log"
).strip()

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _fmt_epoch(t) -> str:
    """Unix epoch → readable UTC string, for the ban timestamps."""
    if not t:
        return ""
    try:
        import datetime
        return datetime.datetime.utcfromtimestamp(int(t)).strftime(
            "%Y-%m-%d %H:%M UTC"
        )
    except (ValueError, OverflowError, OSError):
        return str(t)


def _fmt_duration(s) -> str:
    """Seconds → compact human duration (or 'permanent' for None)."""
    if s is None:
        return "permanent"
    s = int(s)
    if s <= 0:
        return "expired"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m" if m else f"{h}h"
    if m:
        return f"{m}m"
    return f"{sec}s"


templates.env.filters["epoch"] = _fmt_epoch
templates.env.filters["duration"] = _fmt_duration

app = FastAPI(title="SimpleVTT Admin Center", version=APP_VERSION)

# Paths reachable without auth: the healthcheck only (so docker
# compose can probe liveness without baking creds into the
# healthcheck). Everything else is behind basic-auth.
_PUBLIC_PATHS = {"/healthz"}


@app.middleware("http")
async def _basic_auth_mw(request: Request, call_next):
    if request.url.path in _PUBLIC_PATHS:
        return await call_next(request)
    if not header_authorizes(request.headers.get("authorization")):
        return Response(
            "Authentication required.\n",
            status_code=401,
            headers={
                "WWW-Authenticate": 'Basic realm="SimpleVTT Admin Center"',
            },
        )
    return await call_next(request)


@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "service": "admin-center",
        "app_version": APP_VERSION,
        "audit_log_path": AUDIT_LOG_PATH,
        "audit_log_present": Path(AUDIT_LOG_PATH).is_file(),
    }


@app.get("/version")
def version():
    return {"app_version": APP_VERSION, "service": "admin-center"}


@app.get("/api/events")
def api_events(event: str | None = None, limit: int = 500):
    """Recent parsed audit events, newest first. ``event`` filters by
    tag prefix (e.g. ``auth.`` or the exact ``visitor.request``)."""
    limit = max(1, min(int(limit), 5000))
    events = audit_parse.load_events(
        AUDIT_LOG_PATH,
        max_lines=5000,
        event_prefix=event or None,
        newest_first=True,
    )
    return JSONResponse({"count": len(events), "events": events[:limit]})


@app.get("/api/stats")
def api_stats():
    """Traffic statistics rolled up from the audit log."""
    events = audit_parse.load_events(AUDIT_LOG_PATH, max_lines=5000)
    return JSONResponse(stats.summarize(events))


@app.get("/api/fail2ban")
def api_fail2ban():
    """Current fail2ban ban state (jails + currently-banned IPs),
    read directly from the fail2ban sqlite db."""
    return JSONResponse(fail2ban.read_status(now=time.time()))


@app.get("/api/inventory")
def api_inventory():
    """Read-only database data-inventory (row counts per table)."""
    return JSONResponse(inventory.read_inventory())


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, event: str | None = None):
    events = audit_parse.load_events(
        AUDIT_LOG_PATH,
        max_lines=5000,
        event_prefix=event or None,
        newest_first=True,
    )
    summary = stats.summarize(
        audit_parse.load_events(AUDIT_LOG_PATH, max_lines=5000)
    )
    # Distinct event tags present, for the filter dropdown.
    event_tags = sorted(summary["by_event"].keys())
    bans = fail2ban.read_status(now=time.time())
    data_inventory = inventory.read_inventory()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "app_version": APP_VERSION,
            "audit_log_path": AUDIT_LOG_PATH,
            "audit_log_present": Path(AUDIT_LOG_PATH).is_file(),
            "default_password": is_default_password(),
            "summary": summary,
            "events": events[:500],
            "event_tags": event_tags,
            "active_filter": event or "",
            "bans": bans,
            "inventory": data_inventory,
        },
    )
