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
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from ..audit_log import _extract_client_ip
from ..version import APP_VERSION
from . import (
    audit_parse,
    dns_lookup,
    event_help,
    fail2ban,
    inventory,
    login_guard,
    stats,
)
from .basic_auth import check_credentials, header_authorizes, is_default_password

log = logging.getLogger("simplevtt.admin_center")

# Secret for the login session cookie. Prefer a dedicated key; fall
# back to the main app's secret (same operator-set value), then a dev
# default. The cookie name is admin-center-specific so it never
# collides with the main app's `session` cookie on the same host
# (cookies ignore port).
_SESSION_SECRET = (
    os.environ.get("ADMIN_CENTER_SECRET_KEY")
    or os.environ.get("APP_SECRET_KEY")
    or "admin-center-dev-secret-change-me"
)

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
templates.env.filters["explain"] = event_help.explain

app = FastAPI(title="SimpleVTT Admin Center", version=APP_VERSION)


def _safe_next(raw: str | None) -> str:
    """Sanitize a ``?next=`` redirect target to an in-site path so the
    login form can't be turned into an open redirect."""
    if raw and raw.startswith("/") and not raw.startswith("//"):
        return raw
    return "/"


def _is_authed(request: Request) -> bool:
    """A request is authorized if it carries a valid login session OR a
    valid basic-auth header (the latter kept so scripts can still hit
    the JSON APIs without the login dance). We never emit a
    ``WWW-Authenticate`` challenge, so browsers get the login PAGE
    instead of the native popup."""
    if request.session.get("admin_authed"):
        return True
    return header_authorizes(request.headers.get("authorization"))


# Paths reachable without auth: the login page + the healthcheck (so
# docker compose can probe liveness without creds).
def _is_public(path: str) -> bool:
    return path == "/healthz" or path == "/login" or path.startswith("/static")


@app.middleware("http")
async def _auth_mw(request: Request, call_next):
    path = request.url.path
    if _is_public(path) or _is_authed(request):
        return await call_next(request)
    # Unauthenticated. API callers get a clean 401 JSON (no
    # WWW-Authenticate → no browser popup); browser navigations get
    # bounced to the login page with a return path.
    if path.startswith("/api/"):
        return JSONResponse(
            {"detail": "Authentication required. Log in at /login."},
            status_code=401,
        )
    nxt = path + ("?" + request.url.query if request.url.query else "")
    return RedirectResponse(f"/login?next={quote(nxt, safe='')}", status_code=303)


# SessionMiddleware is added AFTER the auth middleware so it sits
# OUTERMOST — the session is decoded before _auth_mw reads it. The
# admin-center-specific cookie name avoids colliding with the main
# app's `session` cookie on the same host.
app.add_middleware(
    SessionMiddleware,
    secret_key=_SESSION_SECRET,
    session_cookie="admin_center_session",
    https_only=False,
)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = "/", error: str = "", locked: int = 0):
    # Already logged in → straight to the dashboard (or the next path).
    if request.session.get("admin_authed"):
        return RedirectResponse(_safe_next(next), status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "app_version": APP_VERSION,
            "next": _safe_next(next),
            "error": error,
            "locked": max(0, int(locked or 0)),
            "default_password": is_default_password(),
        },
    )


@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
):
    ip = _extract_client_ip(request)
    nxt = quote(_safe_next(next), safe="")

    # Brute-force throttle: bounce locked-out IPs before checking creds.
    remaining = login_guard.lockout_remaining(ip, now=time.time())
    if remaining > 0:
        log.warning("admin-center login locked out ip=%s retry_after=%ss", ip, remaining)
        return RedirectResponse(f"/login?next={nxt}&locked={remaining}", status_code=303)

    if check_credentials(username, password):
        login_guard.reset(ip)
        request.session["admin_authed"] = True
        request.session["admin_user"] = username
        return RedirectResponse(_safe_next(next), status_code=303)

    # Failed: record the attempt; if that tipped the IP over the
    # threshold, show the lockout state instead of the generic error.
    login_guard.record_failure(ip, now=time.time())
    log.warning("admin-center login failed ip=%s username=%r", ip, username[:64])
    remaining = login_guard.lockout_remaining(ip, now=time.time())
    if remaining > 0:
        return RedirectResponse(f"/login?next={nxt}&locked={remaining}", status_code=303)
    # 303→GET keeps the form refresh-safe.
    return RedirectResponse(f"/login?next={nxt}&error=1", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


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
def api_events(event: str | None = None, limit: int = 500, dns: int = 0):
    """Recent parsed audit events, newest first. ``event`` filters by
    tag prefix (e.g. ``auth.`` or the exact ``visitor.request``).
    ``dns=1`` adds a ``ptr`` reverse-DNS hostname to each event (opt-in
    — it costs a lookup per unique IP)."""
    limit = max(1, min(int(limit), 5000))
    events = audit_parse.load_events(
        AUDIT_LOG_PATH,
        max_lines=5000,
        event_prefix=event or None,
        newest_first=True,
    )[:limit]
    if dns:
        ptr = dns_lookup.resolve_many(e["fields"].get("ip", "") for e in events)
        for e in events:
            e["ptr"] = ptr.get(e["fields"].get("ip", ""))
    return JSONResponse({"count": len(events), "events": events})


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
def dashboard(request: Request, event: str | None = None, dns: int = 0):
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
    # Opt-in reverse-DNS column: resolve the IPs visible on this render
    # (the event rows + the top-IPs table), deduped + cached.
    dns_on = bool(dns)
    dns_map: dict = {}
    if dns_on:
        ips = [e["fields"].get("ip", "") for e in events[:500]]
        ips += [ip for ip, _ in summary["top_ips"]]
        dns_map = dns_lookup.resolve_many(ips)
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
            "admin_user": request.session.get("admin_user", ""),
            "dns_on": dns_on,
            "dns_map": dns_map,
        },
    )
