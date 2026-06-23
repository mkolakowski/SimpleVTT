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
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from ..audit_log import _extract_client_ip
from ..version import APP_VERSION
from . import (
    audit_parse,
    cloudflare_unban,
    dns_lookup,
    event_help,
    fail2ban,
    fail2ban_control,
    inventory,
    log_control,
    login_guard,
    mfa,
    stats,
    timefmt,
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

# v2.573.0 — harness test-results dashboard. The runner
# (scripts/run_harness.sh) writes harness-<ts>.json reports (counts +
# slowest tests + failures, via scripts/harness_report.py) into
# TEST_RESULTS_DIR, mounted read-only into this container; the /tests page
# reads + visualizes them.
_TEST_RESULTS_DIR = Path(os.getenv(
    "TEST_RESULTS_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "test-results"),
))


def _load_test_run(path: Path) -> "dict | None":
    """Parse one harness-<ts>.json report; tag it with its run id + mtime."""
    import json as _json
    try:
        data = _json.loads(path.read_text())
    except Exception:
        return None
    data["_run_id"] = path.stem.replace("harness-", "")
    try:
        data["_mtime"] = path.stat().st_mtime
    except OSError:
        data["_mtime"] = 0
    return data


def _list_test_runs(limit: int = 30) -> list:
    """Newest-first list of harness run reports (excludes the latest.json
    symlink — the glob only matches harness-*.json files)."""
    if not _TEST_RESULTS_DIR.is_dir():
        return []
    files = sorted(
        _TEST_RESULTS_DIR.glob("harness-*.json"),
        key=lambda p: p.name, reverse=True,
    )
    return [r for r in (_load_test_run(p) for p in files[:limit]) if r]


# v2.573.2 — Phase 1 of docs/plans/admin-center-consolidation.md: an opt-in
# "Admin tools" surface in the Center. OFF by default so an existing
# read-only deployment doesn't silently gain write-admin; the operator sets
# ADMIN_CENTER_ADMIN_TOOLS=true to enable it.
_ADMIN_TOOLS_ENABLED = os.getenv(
    "ADMIN_CENTER_ADMIN_TOOLS", "").strip().lower() in ("1", "true", "yes")


def _demo_mode() -> bool:
    return os.getenv("DEMO_MODE", "").strip().lower() in ("1", "true", "yes")

# Reuse the main site's favicon (baked into the same image at
# app/static/favicon.svg). The admin center has no /static mount, so
# it's served via the dedicated /favicon.svg route below.
_FAVICON_PATH = Path(__file__).resolve().parent.parent / "static" / "favicon.svg"


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


templates.env.filters["epoch"] = timefmt.fmt_epoch
templates.env.filters["duration"] = _fmt_duration
templates.env.filters["explain"] = event_help.explain
# Audit-log line timestamps (app writes UTC) → the display zone.
templates.env.filters["localtime"] = timefmt.fmt_log_ts

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
    # /login/mfa is part of the login flow (reachable mid-login, before
    # the session is fully authed); it self-guards on the mfa_pending
    # session flag.
    return (
        path == "/healthz"
        or path == "/favicon.svg"
        or path == "/favicon.ico"
        or path == "/login"
        or path == "/login/mfa"
        or path.startswith("/static")
    )


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
            # Fail-closed signal: MFA on but no usable TOTP secret.
            "mfa_misconfigured": mfa.mfa_misconfigured(),
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

    # Fail closed: MFA enabled but no usable TOTP secret → refuse every
    # login rather than silently dropping to password-only.
    if mfa.mfa_misconfigured():
        log.error("admin-center login refused: MFA enabled but ADMIN_CENTER_TOTP_SECRET unset/invalid")
        return RedirectResponse(f"/login?next={nxt}&error=1", status_code=303)

    if check_credentials(username, password):
        login_guard.reset(ip)
        if mfa.mfa_enabled():
            # Password OK → require the second factor. mfa_pending alone
            # grants nothing (the auth middleware checks admin_authed).
            request.session["mfa_pending"] = True
            request.session["mfa_user"] = username
            request.session["mfa_next"] = _safe_next(next)
            request.session.pop("admin_authed", None)
            return RedirectResponse("/login/mfa", status_code=303)
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


@app.get("/login/mfa", response_class=HTMLResponse)
def mfa_form(request: Request, error: str = "", locked: int = 0):
    if request.session.get("admin_authed"):
        return RedirectResponse("/", status_code=303)
    # Only reachable mid-login (password already accepted this session).
    if not request.session.get("mfa_pending"):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        "mfa.html",
        {
            "request": request,
            "app_version": APP_VERSION,
            "error": error,
            "locked": max(0, int(locked or 0)),
            "recovery_available": bool(mfa._recovery_code()),
        },
    )


@app.post("/login/mfa")
def mfa_submit(request: Request, code: str = Form("")):
    if not request.session.get("mfa_pending"):
        return RedirectResponse("/login", status_code=303)
    ip = _extract_client_ip(request)

    # Reuse the brute-force throttle for the second-factor step too.
    remaining = login_guard.lockout_remaining(ip, now=time.time())
    if remaining > 0:
        return RedirectResponse(f"/login/mfa?locked={remaining}", status_code=303)

    # Fail closed if the secret vanished between steps.
    if mfa.mfa_misconfigured():
        request.session.clear()
        return RedirectResponse("/login?error=1", status_code=303)

    code = (code or "").strip()
    via_recovery = mfa.recovery_code_accepts(code)
    if mfa.verify_totp(code, now=time.time()) or via_recovery:
        if via_recovery:
            mfa.mark_recovery_used()
            log.warning(
                "admin-center MFA RECOVERY CODE used ip=%s user=%r — rotate "
                "ADMIN_CENTER_RECOVERY_CODE now", ip,
                request.session.get("mfa_user", ""),
            )
        login_guard.reset(ip)
        nxt = request.session.get("mfa_next", "/")
        request.session["admin_authed"] = True
        request.session["admin_user"] = request.session.get("mfa_user", "")
        for k in ("mfa_pending", "mfa_user", "mfa_next"):
            request.session.pop(k, None)
        return RedirectResponse(_safe_next(nxt), status_code=303)

    # Bad code → throttle + re-prompt.
    login_guard.record_failure(ip, now=time.time())
    log.warning("admin-center MFA code failed ip=%s", ip)
    remaining = login_guard.lockout_remaining(ip, now=time.time())
    if remaining > 0:
        return RedirectResponse(f"/login/mfa?locked={remaining}", status_code=303)
    return RedirectResponse("/login/mfa?error=1", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/favicon.svg")
@app.get("/favicon.ico")
def favicon():
    """Serve the same favicon as the main site (image-baked SVG)."""
    if _FAVICON_PATH.is_file():
        return FileResponse(str(_FAVICON_PATH), media_type="image/svg+xml")
    return Response(status_code=404)


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


@app.post("/logs/clear")
def logs_clear(request: Request):
    """Clear the audit log (truncate + drop rotated backups). Leaves a
    ``admin_center.log_cleared`` marker recording who did it, so the
    clear is itself auditable. Form POST → redirects to the dashboard."""
    import datetime
    user = request.session.get("admin_user", "")
    ip = _extract_client_ip(request)
    # UTC asctime to match what the app's logger writes (the dashboard's
    # localtime filter parses it as UTC).
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    marker = (
        f'{ts} WARNING simplevtt.audit: admin_center.log_cleared '
        f'ip={ip} by="{user}"'
    )
    result = log_control.clear_audit_log(AUDIT_LOG_PATH, marker_line=marker)
    if result.get("ok"):
        log.warning("admin-center audit log CLEARED by=%r ip=%s", user, ip)
        return RedirectResponse("/?logs_cleared=1", status_code=303)
    return RedirectResponse(
        f"/?logs_error={quote(result.get('error', 'failed'), safe='')}",
        status_code=303,
    )


@app.post("/fail2ban/unban")
async def fail2ban_unban(request: Request, ip: str = Form("")):
    """Unban ``ip`` everywhere it might be banned.

    1. Local fail2ban jails — via the shared control spool the fail2ban
       container's watcher drains (the admin center can't reach
       fail2ban's root-only socket as the non-root appuser).
    2. The Cloudflare edge — removes any IP Access Rule for the IP, if
       the Cloudflare client is configured (bans pushed by the
       cloudflare-bouncer action or the in-app "Ban IP at edge" button).

    Form POST → redirects back to the dashboard (the button lives in the
    bans table)."""
    result = fail2ban_control.request_unban(ip)
    if not result.get("ok"):
        return RedirectResponse(
            f"/?unban_error={quote(result.get('error', 'failed'), safe='')}",
            status_code=303,
        )
    log.info("admin-center queued unban ip=%s by=%r", result["ip"],
             request.session.get("admin_user", ""))
    # Also lift any Cloudflare edge ban. None → client not configured.
    cf_removed = await cloudflare_unban.unban_ip(result["ip"])
    loc = f"/?unbanned={quote(result['ip'], safe='')}"
    if cf_removed is not None:
        loc += f"&cf={cf_removed}"
    return RedirectResponse(loc, status_code=303)


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    event: str | None = None,
    dns: int = 0,
    unbanned: str = "",
    unban_error: str = "",
    cf: int = -1,
    logs_cleared: int = 0,
    logs_error: str = "",
):
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
            "unbanned": unbanned,
            "unban_error": unban_error,
            "cf_removed": cf,
            "logs_cleared": logs_cleared,
            "logs_error": logs_error,
            "admin_tools_enabled": _ADMIN_TOOLS_ENABLED,
        },
    )


@app.get("/tests", response_class=HTMLResponse)
def tests_dashboard(request: Request):
    """v2.573.0 — harness test-results dashboard: pass/fail summary, the
    slowest tests, the failure list, and a run-history trend, from the JSON
    reports the harness runner writes. Read-only; auto-gated by the auth
    middleware. Shows an empty-state when no runs are present (e.g. in
    production, where the suite isn't run)."""
    runs = _list_test_runs(limit=30)
    return templates.TemplateResponse(
        "tests.html",
        {
            "request": request,
            "app_version": APP_VERSION,
            "admin_user": request.session.get("admin_user", ""),
            "results_dir": str(_TEST_RESULTS_DIR),
            "latest": runs[0] if runs else None,
            "runs": runs,
        },
    )


# ── Admin tools (Phase 1 — opt-in, demo operator tools) ──────────────────────
_TOOLS_DISABLED = HTMLResponse(
    "<h1>Admin tools are disabled</h1><p>Set "
    "<code>ADMIN_CENTER_ADMIN_TOOLS=true</code> to enable this surface.</p>",
    status_code=404,
)


@app.get("/tools", response_class=HTMLResponse)
def admin_tools(request: Request, minted: str = "", reset: str = "", err: str = ""):
    """Operator tools page: demo reset + demo magic-link minting, moved here
    from the main app's /admin portal. Opt-in via ADMIN_CENTER_ADMIN_TOOLS;
    auto-gated by the auth middleware."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    from ..demo_magic_link import magic_link_enabled
    from ..demo_seed import DEMO_EMAILS
    return templates.TemplateResponse(
        "tools.html",
        {
            "request": request,
            "app_version": APP_VERSION,
            "admin_user": request.session.get("admin_user", ""),
            "demo_mode": _demo_mode(),
            "magic_link_enabled": magic_link_enabled(),
            "demo_emails": sorted(DEMO_EMAILS),
            "minted": minted,
            "reset": reset,
            "err": err,
        },
    )


@app.post("/tools/demo/mint-magic-link")
def admin_tools_mint(request: Request, sub: str = Form(...)):
    """Mint a one-time demo login link (non-destructive). Double-gated by
    ADMIN_CENTER_ADMIN_TOOLS + the app's magic_link_enabled()."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    from ..demo_magic_link import magic_link_enabled, mint_token
    from ..demo_seed import DEMO_EMAILS
    from ..config import get_settings
    if not magic_link_enabled():
        return RedirectResponse("/tools?err=Magic-link+login+is+not+enabled", status_code=303)
    sub_norm = sub.strip().lower()
    if sub_norm not in DEMO_EMAILS:
        return RedirectResponse("/tools?err=Unknown+demo+account", status_code=303)
    token = mint_token(sub_norm)
    base_url = get_settings().app.base_url.rstrip("/")
    url = f"{base_url}/demo-login?token={token}"
    log.info("admin-center operator %r minted a demo magic link for %s",
             request.session.get("admin_user", "?"), sub_norm)
    return RedirectResponse(f"/tools?minted={quote(url)}", status_code=303)


@app.post("/tools/demo/reset")
def admin_tools_demo_reset(request: Request):
    """DESTRUCTIVE: wipe + reseed the demo database. Double-gated by
    ADMIN_CENTER_ADMIN_TOOLS + DEMO_MODE (so it can never fire in
    production), and audit-logged with the operator identity."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    if not _demo_mode():
        return RedirectResponse("/tools?err=DEMO_MODE+is+not+enabled", status_code=303)
    from ..demo_seed import reset_and_reseed
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    db = SessionLocal()
    try:
        counts = reset_and_reseed(db)
    except Exception as exc:  # pragma: no cover - surfaced to the operator
        log.exception("admin-center demo reset failed")
        return RedirectResponse(f"/tools?err={quote('Reset failed: ' + str(exc))}", status_code=303)
    finally:
        db.close()
    log.warning("admin-center operator %r triggered a demo reset: %s", operator, counts)
    return RedirectResponse(f"/tools?reset={quote(str(counts))}", status_code=303)
