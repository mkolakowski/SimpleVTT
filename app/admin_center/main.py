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

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
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


def _fmt_bytes(n) -> str:
    """Compact human byte size (e.g. 0 B, 4.2 KB, 1.3 GB)."""
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


templates.env.filters["epoch"] = timefmt.fmt_epoch
templates.env.filters["duration"] = _fmt_duration
templates.env.filters["bytes"] = _fmt_bytes
# v2.589.1 — expose the admin-tools flag to every template so the shared
# top-bar partial (_nav.html) can gate the write-surface links without each
# route having to pass it explicitly.
templates.env.globals["admin_tools_enabled"] = _ADMIN_TOOLS_ENABLED
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


_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _csrf_origin_ok(request: Request) -> bool:
    """CSRF defense (v2.599.8): reject cross-origin browser state changes.

    A browser always sends ``Origin`` (and/or ``Referer``) on a state-changing
    request, so if one is present its host MUST match our ``Host``. Header-less
    callers (CLI / API / the harness) are allowed — they aren't driven by a
    victim's browser, so they can't be a CSRF vector. We compare hosts only
    (not scheme): behind a TLS-terminating proxy the app sees ``http``
    internally while the browser's Origin is ``https``. Complements the
    SameSite=Lax cookie — defense-in-depth on the destructive operator routes.
    """
    host = request.headers.get("host", "")
    for hdr in ("origin", "referer"):
        val = request.headers.get(hdr)
        if val:
            from urllib.parse import urlsplit
            return urlsplit(val).netloc == host
    return True  # no Origin/Referer → non-browser client


@app.middleware("http")
async def _auth_mw(request: Request, call_next):
    path = request.url.path
    if request.method in _UNSAFE_METHODS and not _csrf_origin_ok(request):
        return JSONResponse(
            {"detail": "CSRF check failed: cross-origin request rejected."},
            status_code=403,
        )
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
# v2.599.7 — session cookie hardening (see app/main.py). same_site=lax explicit
# + env-driven Secure flag (default off for HTTP dev / the harness).
_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in ("1", "true", "yes", "on")
app.add_middleware(
    SessionMiddleware,
    secret_key=_SESSION_SECRET,
    session_cookie="admin_center_session",
    same_site="lax",
    https_only=_COOKIE_SECURE,
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


@app.get("/api/storage")
def api_storage():
    """Read-only storage accounting: per-user + per-campaign byte
    breakdowns of uploaded files (Arc B1 of
    docs/plans/app-wide-roles-and-storage.md)."""
    from . import storage as _storage
    return JSONResponse(_storage.read_storage())


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


# ── Demo self-test (live game-loop smoke test) ───────────────────────────────
@app.get("/selftest", response_class=HTMLResponse)
def selftest_page(request: Request):
    """Live demo self-test: drive token movement + (Phase 2) combat rounds
    against every demo campaign and stream a nested pass/fail report. Opt-in via
    ADMIN_CENTER_ADMIN_TOOLS (it mutates campaign state, then restores it) and
    only meaningful in DEMO_MODE (needs the demo campaigns + accounts)."""
    from . import selftest
    return templates.TemplateResponse(
        "selftest.html",
        {
            "request": request,
            "app_version": APP_VERSION,
            "admin_user": request.session.get("admin_user", ""),
            "enabled": _ADMIN_TOOLS_ENABLED,
            "demo_mode": _demo_mode(),
            "status": selftest.run_status(),
            "history": selftest.list_runs() if (_ADMIN_TOOLS_ENABLED and _demo_mode()) else [],
            "campaigns": selftest.list_campaigns() if (_ADMIN_TOOLS_ENABLED and _demo_mode()) else [],
            "all_phases": list(selftest._ALL_PHASES),
        },
    )


@app.post("/selftest/run")
async def selftest_run(request: Request):
    """Kick off a background self-test run over an optional subset. Gated by
    ADMIN_CENTER_ADMIN_TOOLS + DEMO_MODE. Optional JSON body:
    ``{campaigns: [id,...], phases: ["movement","combat","spells","gates"]}``
    (both omitted → full run)."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    if not _demo_mode():
        return RedirectResponse(
            "/selftest?err=Self-test+needs+DEMO_MODE", status_code=303)
    from . import selftest
    campaign_ids, phases, step_delay = None, None, None
    try:
        body = await request.json()
        if isinstance(body, dict):
            campaign_ids = body.get("campaigns") or None
            phases = body.get("phases") or None
            if body.get("slow"):
                step_delay = selftest._SLOW_STEP_DELAY
            elif body.get("step_delay") is not None:
                step_delay = float(body.get("step_delay"))
    except Exception:  # noqa: BLE001 — no/invalid body → full run
        pass
    started = selftest.start_run(
        campaign_ids=campaign_ids, phases=phases, step_delay=step_delay)
    log.info("admin-center operator %r %s a demo self-test (campaigns=%s, phases=%s, slow=%s)",
             request.session.get("admin_user", "?"),
             "started" if started else "re-requested (already running)",
             campaign_ids or "all", phases or "all", step_delay is not None)
    return JSONResponse({"started": started, "state": selftest.run_status().get("state")})


@app.post("/selftest/reseed")
async def selftest_reseed(request: Request):
    """Wipe + reseed just the selected demo campaigns to their pristine state.
    Separate from running the self-test. Gated by ADMIN_CENTER_ADMIN_TOOLS +
    DEMO_MODE. Body: ``{campaigns: [id, ...]}`` (required)."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    if not _demo_mode():
        return JSONResponse({"error": "reseed needs DEMO_MODE"}, status_code=400)
    from . import selftest
    campaign_ids = None
    try:
        body = await request.json()
        if isinstance(body, dict):
            campaign_ids = body.get("campaigns") or None
    except Exception:  # noqa: BLE001
        pass
    if not campaign_ids:
        return JSONResponse({"error": "no campaigns given"}, status_code=400)
    results = selftest.reseed_campaigns(campaign_ids)
    log.info("admin-center operator %r reseeded demo campaigns %s -> %s",
             request.session.get("admin_user", "?"), campaign_ids, results)
    return JSONResponse({"results": results})


@app.get("/selftest/run-status")
def selftest_run_status(request: Request):
    """Current run state + the growing report snapshot — polled by the page."""
    if not _ADMIN_TOOLS_ENABLED:
        return JSONResponse({"state": "disabled"})
    from . import selftest
    return JSONResponse(selftest.run_status())


@app.get("/selftest/history")
def selftest_history_list(request: Request):
    """Newest-first run-history headers — lets the page refresh the table after
    a run without a full reload."""
    if not _ADMIN_TOOLS_ENABLED:
        return JSONResponse({"runs": []})
    from . import selftest
    return JSONResponse({"runs": selftest.list_runs()})


@app.get("/selftest/history/{run_id}")
def selftest_history(request: Request, run_id: str):
    """Full archived report for a past run (id from the history table). 404 if
    the id is unknown/invalid."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    from . import selftest
    rep = selftest.load_run(run_id)
    if rep is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return JSONResponse(rep)


# ── Admin tools (Phase 1 — opt-in, demo operator tools) ──────────────────────
_TOOLS_DISABLED = HTMLResponse(
    "<h1>Admin tools are disabled</h1><p>Set "
    "<code>ADMIN_CENTER_ADMIN_TOOLS=true</code> to enable this surface.</p>",
    status_code=404,
)


@app.get("/storage", response_class=HTMLResponse)
def storage_dashboard(request: Request):
    """v2.588.0 — storage accounting dashboard: per-user + per-campaign byte
    breakdowns of uploaded files (Arc B1 of
    docs/plans/app-wide-roles-and-storage.md). Read-only; auto-gated by the
    auth middleware."""
    from . import storage as _storage
    report = _storage.read_storage()
    return templates.TemplateResponse(
        "storage.html",
        {
            "request": request,
            "app_version": APP_VERSION,
            "admin_user": request.session.get("admin_user", ""),
            "report": report,
        },
    )


@app.get("/feedback", response_class=HTMLResponse)
def admin_feedback(request: Request, status: str = "", kind: str = "", done: str = ""):
    """v2.726.0 — user-submitted suggestions / issue reports (the in-app
    "💡 Suggest" button), with inline triage. Read + light triage available
    to any authed operator (auto-gated by the auth middleware); not behind
    ADMIN_CENTER_ADMIN_TOOLS, like Storage / Tests. Optional ?status= / ?kind=
    filters."""
    from . import feedback_admin
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        rows = feedback_admin.list_suggestions(
            db, status=status or None, kind=kind or None)
        open_n = feedback_admin.open_count(db)
    finally:
        db.close()
    return templates.TemplateResponse(
        "feedback.html",
        {
            "request": request,
            "app_version": APP_VERSION,
            "admin_user": request.session.get("admin_user", ""),
            "suggestions": rows,
            "open_count": open_n,
            "filter_status": status,
            "filter_kind": kind,
            "done": done,
            "statuses": ["new", "in_progress", "resolved", "wont_fix"],
        },
    )


@app.post("/feedback/{suggestion_id}/update")
def admin_feedback_update(
    request: Request, suggestion_id: int,
    status: str = Form(""), admin_note: str = Form(""),
):
    """Set a report's status + admin note. Authed-operator gated (middleware);
    no MFA gate — triage is non-destructive."""
    from . import feedback_admin
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        feedback_admin.update_suggestion(
            db, suggestion_id,
            status=status or None, admin_note=admin_note)
    finally:
        db.close()
    return RedirectResponse("/feedback?done=updated", status_code=303)


@app.post("/feedback/{suggestion_id}/delete")
def admin_feedback_delete(request: Request, suggestion_id: int):
    """Delete a report. Authed-operator gated (middleware)."""
    from . import feedback_admin
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        feedback_admin.delete_suggestion(db, suggestion_id)
    finally:
        db.close()
    return RedirectResponse("/feedback?done=deleted", status_code=303)


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


# ── Backups (Phase 8 — operator backup schedule/retention) ────────────────────
# Opt-in via ADMIN_CENTER_ADMIN_TOOLS (operator infra). Edits a settings file on
# the shared backup volume that the sidecar watch-loops; read-only in DEMO_MODE.

def _restore_allowed(request: Request) -> bool:
    """Restore is the most destructive operator action (it overwrites the whole
    database + media), so it's gated harder than the rest of the page: tools on,
    NOT a demo instance, and — when MFA is configured — an MFA-verified session.
    """
    from . import backup_admin
    if not _ADMIN_TOOLS_ENABLED or backup_admin.demo_mode_active():
        return False
    if mfa.mfa_enabled() and not _mfa_verified(request):
        return False
    return True


@app.get("/backups", response_class=HTMLResponse)
def backups_page(request: Request, saved: str = "", ran: str = "", err: str = "", restored: str = "", deleted: str = ""):
    """Backup schedule + retention editor, backup listing (download + restore),
    and run-now. Opt-in via ADMIN_CENTER_ADMIN_TOOLS; auto-gated by the auth
    middleware."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    from . import backup_admin
    return templates.TemplateResponse(
        "backups.html",
        {
            "request": request,
            "app_version": APP_VERSION,
            "admin_user": request.session.get("admin_user", ""),
            "settings": backup_admin.read_settings(),
            "backups": backup_admin.list_backups(),
            "demo_mode": backup_admin.demo_mode_active(),
            "demo_override": backup_admin.demo_override_active(),
            "restore_allowed": _restore_allowed(request),
            "restore_pending": backup_admin.restore_pending(),
            "last_restore": backup_admin.last_restore_result(),
            "saved": saved,
            "ran": ran,
            "err": err,
            "restored": restored,
            "deleted": deleted,
        },
    )


@app.post("/backups/delete")
def backups_delete(request: Request, bucket: str = Form(...), ts: str = Form(...)):
    """Delete a backup run's artifacts (the dump + tarballs + tag). Opt-in via
    ADMIN_CENTER_ADMIN_TOOLS; confirmed client-side before posting. Operates on
    existing files, so it's allowed regardless of demo mode (unlike taking a new
    backup)."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    from . import backup_admin
    n = backup_admin.delete_backup(bucket, ts)
    if not n:
        return RedirectResponse("/backups?err=Backup+not+found", status_code=303)
    log.warning("admin-center operator %r deleted backup %s/%s (%d files)",
                request.session.get("admin_user", "?"), bucket, ts, n)
    return RedirectResponse(f"/backups?deleted={quote(ts)}", status_code=303)


@app.post("/backups/restore")
def backups_restore(request: Request, bucket: str = Form(...), ts: str = Form(...)):
    """Queue a DESTRUCTIVE restore of the selected backup. The sidecar takes a
    tagged safety backup first, then overwrites the database + homebrew +
    uploads. Refused in DEMO_MODE / without the restore gate."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    from datetime import datetime, timezone

    from . import backup_admin
    if not _restore_allowed(request):
        return RedirectResponse("/backups?err=Restore+is+not+available+here", status_code=303)
    operator = request.session.get("admin_user", "?")
    ok = backup_admin.request_restore(
        bucket, ts, requested_by=operator,
        now_iso=datetime.now(timezone.utc).isoformat(),
    )
    if not ok:
        return RedirectResponse("/backups?err=Could+not+queue+restore+(unknown+backup+or+one+already+pending)", status_code=303)
    log.warning("admin-center operator %r queued a RESTORE of %s/%s", operator, bucket, ts)
    return RedirectResponse(f"/backups?restored={quote(ts)}", status_code=303)


@app.post("/backups/settings")
def backups_save(
    request: Request,
    cron: str = Form(...),
    keep_daily: str = Form(...),
    keep_weekly: str = Form(...),
):
    """Persist the schedule + retention to the shared settings file. Refused in
    DEMO_MODE (backups are disabled there)."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    from datetime import datetime, timezone

    from . import backup_admin
    if backup_admin.demo_mode_active():
        return RedirectResponse("/backups?err=Backups+are+disabled+in+demo+mode", status_code=303)
    operator = request.session.get("admin_user", "?")
    try:
        backup_admin.write_settings(
            cron=cron, keep_daily=keep_daily, keep_weekly=keep_weekly,
            updated_by=operator, now_iso=datetime.now(timezone.utc).isoformat(),
        )
    except ValueError as exc:
        return RedirectResponse(f"/backups?err={quote(str(exc))}", status_code=303)
    log.info("admin-center operator %r updated backup settings", operator)
    return RedirectResponse("/backups?saved=1", status_code=303)


@app.post("/backups/run")
def backups_run(request: Request):
    """Drop the run-now trigger the sidecar watch-loop picks up. Refused in
    DEMO_MODE."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    from . import backup_admin
    if backup_admin.demo_mode_active():
        return RedirectResponse("/backups?err=Backups+are+disabled+in+demo+mode", status_code=303)
    backup_admin.trigger_run()
    log.info("admin-center operator %r triggered an on-demand backup",
             request.session.get("admin_user", "?"))
    return RedirectResponse("/backups?ran=1", status_code=303)


@app.get("/backups/run-status")
def backups_run_status(request: Request):
    """The sidecar's progress for the current/last backup run — polled by the
    'Back up now' progress toast. JSON; opt-in via ADMIN_CENTER_ADMIN_TOOLS."""
    if not _ADMIN_TOOLS_ENABLED:
        return JSONResponse({"state": "idle"})
    from . import backup_admin
    return JSONResponse(backup_admin.run_status())


@app.get("/backups/download")
def backups_download(request: Request, bucket: str = "", ts: str = ""):
    """Download a whole backup run as a single ``.zip`` bundling its SQL dump +
    homebrew tarball. The bucket + timestamp are validated (allowlisted bucket,
    alnum timestamp, each filename re-checked) so the path can't traverse out of
    the backup dir. The artifacts are already gzip-compressed, so the zip is
    STORED (no pointless re-compression)."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    import io
    import zipfile

    from . import backup_admin
    paths = backup_admin.backup_files_for(bucket, ts)
    if not paths:
        raise HTTPException(status_code=404, detail="Backup not found.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for p in paths:
            zf.write(str(p), p.name)
    log.info("admin-center operator %r downloaded backup %s/%s (%d files)",
             request.session.get("admin_user", "?"), bucket, ts, len(paths))
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="simplevtt-backup-{ts}.zip"'},
    )


# ── User admin (Phase 2 — opt-in, MFA-gated for destructive ops) ──────────────
# Phase 2a: the read-only user list + non-destructive create. Phase 2b
# (this surface): the destructive ops (disable / reset-password / delete),
# refused unless MFA is enabled + the session is MFA-verified. All gated
# by ADMIN_CENTER_ADMIN_TOOLS (default off).


def _mfa_verified(request: Request) -> bool:
    """True iff this request carries an interactively MFA-verified login
    session — MFA enabled AND the session reached ``admin_authed`` (which,
    when MFA is on, only happens after the second-factor step). A
    basic-auth *header* caller has no session ``admin_authed``, so it is
    never MFA-verified — destructive ops require the interactive login."""
    return mfa.mfa_enabled() and bool(request.session.get("admin_authed"))


# 403 returned when a destructive user op is attempted without an
# MFA-verified session (the Phase 2 security gate).
_MFA_REQUIRED = HTMLResponse(
    "<h1>MFA required</h1><p>Destructive user-admin actions are refused "
    "unless <code>ADMIN_CENTER_MFA_ENABLED</code> is on and you have "
    "completed the second-factor step this session.</p>",
    status_code=403,
)


@app.get("/users", response_class=HTMLResponse)
def admin_users(request: Request, created: str = "", err: str = "", done: str = ""):
    """User-admin list + create form. Opt-in via ADMIN_CENTER_ADMIN_TOOLS;
    auto-gated by the auth middleware. Destructive per-row controls render
    only when the session is MFA-verified."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    from . import user_admin
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        users = user_admin.list_users(db)
        return templates.TemplateResponse(
            "users.html",
            {
                "request": request,
                "app_version": APP_VERSION,
                "admin_user": request.session.get("admin_user", ""),
                "users": users,
                "created": created,
                "err": err,
                "done": done,
                "mfa_verified": _mfa_verified(request),
                "mfa_enabled": mfa.mfa_enabled(),
            },
        )
    finally:
        db.close()


@app.post("/users/create")
def admin_users_create(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(""),
    password: str = Form(...),
    is_gm: str = Form(None),
    is_admin: str = Form(None),
):
    """Create a local user account (non-destructive — no MFA gate). Audited
    to the operator identity. v2.606.1 — optional GM/admin pre-grants are
    honored ONLY when the session is MFA-verified (mirrors the per-row role
    toggles, which are MFA-gated); a non-MFA create ignores them and makes a
    plain account."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    from . import operator_audit, user_admin
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    _mfa = _mfa_verified(request)
    _want_gm = bool(is_gm) and _mfa
    _want_admin = True if (bool(is_admin) and _mfa) else None
    db = SessionLocal()
    try:
        try:
            u = user_admin.create_user(
                db, email=email, display_name=display_name, password=password,
                is_gm=_want_gm, is_admin=_want_admin,
            )
        except user_admin.UserAdminError as exc:
            return RedirectResponse(f"/users?err={quote(str(exc))}", status_code=303)
        operator_audit.record(
            "admin.user_create", operator=operator, target=u.email,
            request=request, notes=f"display_name={u.display_name[:60]}",
        )
        log.warning("admin-center operator %r created user %s", operator, u.email)
        return RedirectResponse(f"/users?created={quote(u.email)}", status_code=303)
    finally:
        db.close()


def _destructive_gate(request: Request):
    """Shared gate for the destructive user ops. Returns a Response to
    short-circuit (404 when admin-tools off, 403 when not MFA-verified), or
    None when the action may proceed."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    if not _mfa_verified(request):
        return _MFA_REQUIRED
    return None


@app.post("/users/{user_id}/disable")
def admin_users_disable(request: Request, user_id: int):
    """Toggle a user's disabled flag. MFA-gated + audited."""
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    from . import operator_audit, user_admin
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    db = SessionLocal()
    try:
        try:
            u, disabled = user_admin.set_user_disabled(db, user_id)
        except user_admin.UserAdminError as exc:
            return RedirectResponse(f"/users?err={quote(str(exc))}", status_code=303)
        action = "admin.user_disable" if disabled else "admin.user_enable"
        operator_audit.record(action, operator=operator, target=u.email, request=request)
        log.warning("admin-center operator %r %s user %s", operator, action, u.email)
        verb = "disabled" if disabled else "enabled"
        return RedirectResponse(f"/users?done={quote(verb + ' ' + u.email)}", status_code=303)
    finally:
        db.close()


@app.post("/users/{user_id}/reset-password")
def admin_users_reset_password(
    request: Request, user_id: int, new_password: str = Form(...),
):
    """Reset a user's password. MFA-gated + audited. The new password is
    never logged — only that a reset happened to this user."""
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    from . import operator_audit, user_admin
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    db = SessionLocal()
    try:
        try:
            u = user_admin.reset_password(db, user_id, new_password=new_password)
        except user_admin.UserAdminError as exc:
            return RedirectResponse(f"/users?err={quote(str(exc))}", status_code=303)
        operator_audit.record(
            "admin.user_password_reset", operator=operator, target=u.email, request=request,
        )
        log.warning("admin-center operator %r reset password for %s", operator, u.email)
        return RedirectResponse(f"/users?done={quote('password reset for ' + u.email)}", status_code=303)
    finally:
        db.close()


@app.post("/users/{user_id}/delete")
def admin_users_delete(request: Request, user_id: int):
    """Delete a user. MFA-gated + audited (the email is captured before the
    delete so the audit line keeps a human-readable target)."""
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    from . import operator_audit, user_admin
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    db = SessionLocal()
    try:
        try:
            target_email = user_admin.delete_user(db, user_id)
        except user_admin.UserAdminError as exc:
            return RedirectResponse(f"/users?err={quote(str(exc))}", status_code=303)
        operator_audit.record(
            "admin.user_delete", operator=operator, target=target_email, request=request,
        )
        log.warning("admin-center operator %r deleted user %s", operator, target_email)
        return RedirectResponse(f"/users?done={quote('deleted ' + target_email)}", status_code=303)
    finally:
        db.close()


@app.post("/users/{user_id}/role")
def admin_users_set_role(
    request: Request, user_id: int, role: str = Form(...), value: str = Form(""),
):
    """Grant/revoke an app-wide role (gm/admin) on a user. MFA-gated +
    audited. value truthy → grant, else revoke. See
    docs/plans/app-wide-roles-and-storage.md."""
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    if role not in ("gm", "admin"):
        return RedirectResponse("/users?err=Unknown+role", status_code=303)
    grant = value.strip().lower() in ("1", "true", "yes", "on", "grant")
    from . import operator_audit, user_admin
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    db = SessionLocal()
    try:
        try:
            u = user_admin.set_role(db, user_id, role=role, value=grant)
        except user_admin.UserAdminError as exc:
            return RedirectResponse(f"/users?err={quote(str(exc))}", status_code=303)
        action = "admin.user_role_grant" if grant else "admin.user_role_revoke"
        operator_audit.record(
            action, operator=operator, target=u.email, request=request,
            notes=f"role={role}",
        )
        log.warning("admin-center operator %r %s %s for %s",
                    operator, action, role, u.email)
        verb = "granted" if grant else "revoked"
        return RedirectResponse(
            f"/users?done={quote(f'{verb} {role} for {u.email}')}", status_code=303)
    finally:
        db.close()


@app.post("/users/{user_id}/storage-limit")
def admin_users_storage_limit(request: Request, user_id: int, limit_mb: str = Form("")):
    """Set/clear a user's aggregate storage limit (MB; blank/0 = unlimited).
    MFA-gated + audited. See docs/plans/app-wide-roles-and-storage.md."""
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    try:
        mb = float(limit_mb) if limit_mb.strip() else 0
    except ValueError:
        return RedirectResponse("/users?err=Invalid+limit", status_code=303)
    limit_bytes = int(mb * 1024 * 1024) if mb > 0 else 0
    from . import operator_audit, user_admin
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    db = SessionLocal()
    try:
        try:
            u = user_admin.set_storage_limit(db, user_id, limit_bytes=limit_bytes)
        except user_admin.UserAdminError as exc:
            return RedirectResponse(f"/users?err={quote(str(exc))}", status_code=303)
        operator_audit.record(
            "admin.user_storage_limit", operator=operator, target=u.email,
            request=request, notes=f"limit_bytes={limit_bytes or 'unlimited'}",
        )
        msg = f"storage limit {f'{mb:g} MB' if limit_bytes else 'cleared'} for {u.email}"
        return RedirectResponse(f"/users?done={quote(msg)}", status_code=303)
    finally:
        db.close()


@app.post("/users/{user_id}/scrub-audit-log")
def admin_users_scrub_audit(request: Request, user_id: int, email: str = Form("")):
    """GDPR Art. 17 pseudonymization of a user's identifiers in the audit
    log (rewrites matching lines to an opaque ``<deleted-…>`` token; never
    deletes lines, preserves ip/ua/event-tag). MFA-gated (destructive — it
    rewrites the audit-log files). Returns the same JSON contract as the
    in-app route; the action is recorded against the *pseudonym* (the real
    email is never written back into the freshly-scrubbed log), so the scrub
    runs BEFORE the operator-audit append."""
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    addr = (email or "").strip()
    if not addr:
        return JSONResponse({"detail": "email is required"}, status_code=400)
    from ..audit_scrub import scrub_user_from_audit_log
    from . import operator_audit
    operator = request.session.get("admin_user", "?")
    summary = scrub_user_from_audit_log(user_id=user_id, email=addr)
    operator_audit.record(
        "admin.user_audit_scrub", operator=operator, target=summary["pseudonym"],
        request=request,
        notes=(
            f"audit-log scrub: {summary['lines_rewritten']} line(s) "
            f"pseudonymized across {summary['files_scanned']} file(s)"
        ),
    )
    log.warning("admin-center operator %r scrubbed audit log for user_id=%s (%s lines)",
                operator, user_id, summary["lines_rewritten"])
    return {
        "ok": True,
        "user_id": user_id,
        "pseudonym": summary["pseudonym"],
        "files_scanned": summary["files_scanned"],
        "lines_rewritten": summary["lines_rewritten"],
    }


# ── Campaign admin (Phase 3 — opt-in; delete MFA-gated) ───────────────────────
# Phase 3a (this surface): a campaign list + read-only detail (members /
# characters / maps / system) + the headline destructive action, delete
# campaign (refused unless MFA-verified, audited). Member / character /
# map / system management is a later 3b. All gated by
# ADMIN_CENTER_ADMIN_TOOLS (default off).


@app.get("/campaigns", response_class=HTMLResponse)
def admin_campaigns(request: Request, done: str = "", err: str = ""):
    """Campaign list. Opt-in via ADMIN_CENTER_ADMIN_TOOLS."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    from . import campaign_admin
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        campaigns = campaign_admin.list_campaigns(db)
        return templates.TemplateResponse(
            "campaigns.html",
            {
                "request": request,
                "app_version": APP_VERSION,
                "admin_user": request.session.get("admin_user", ""),
                "campaigns": campaigns,
                "done": done,
                "err": err,
            },
        )
    finally:
        db.close()


@app.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
def admin_campaign_detail(request: Request, campaign_id: int, done: str = "", err: str = ""):
    """Campaign detail. Read-only sections always render; the management
    controls (members / system / characters / delete) render only on an
    MFA-verified session."""
    if not _ADMIN_TOOLS_ENABLED:
        return _TOOLS_DISABLED
    from . import campaign_admin
    from ..database import SessionLocal
    from ..game_systems import system_choices
    from .. import stats_service
    db = SessionLocal()
    try:
        try:
            detail = campaign_admin.get_campaign_detail(db, campaign_id)
        except campaign_admin.CampaignAdminError as exc:
            return RedirectResponse(f"/campaigns?err={quote(str(exc))}", status_code=303)
        # v2.737.0 — campaign activity report (same data as the main app's
        # GM Reporting page), surfaced here so operators can see per-campaign
        # engagement without the tabletop.
        report = stats_service.campaign_activity_report(db, campaign_id)
        return templates.TemplateResponse(
            "campaign_detail.html",
            {
                "request": request,
                "app_version": APP_VERSION,
                "admin_user": request.session.get("admin_user", ""),
                "campaign": detail["campaign"],
                "gm_email": detail["gm_email"],
                "members": detail["members"],
                "characters": detail["characters"],
                "maps": detail["maps"],
                "non_members": detail["non_members"],
                "all_users": detail["all_users"],
                "system_choices": system_choices(),
                "mfa_verified": _mfa_verified(request),
                "mfa_enabled": mfa.mfa_enabled(),
                "report": report,
                "done": done,
                "err": err,
            },
        )
    finally:
        db.close()


@app.post("/campaigns/{campaign_id}/delete")
def admin_campaign_delete(request: Request, campaign_id: int):
    """Delete a campaign (and its cascaded data). MFA-gated + audited."""
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    from . import campaign_admin, operator_audit
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    db = SessionLocal()
    try:
        try:
            name = campaign_admin.delete_campaign(db, campaign_id)
        except campaign_admin.CampaignAdminError as exc:
            return RedirectResponse(f"/campaigns?err={quote(str(exc))}", status_code=303)
        operator_audit.record(
            "admin.campaign_delete", operator=operator, target=name, request=request,
            notes=f"campaign:{campaign_id}",
        )
        log.warning("admin-center operator %r deleted campaign %s (id=%s)", operator, name, campaign_id)
        return RedirectResponse(f"/campaigns?done={quote('deleted ' + name)}", status_code=303)
    finally:
        db.close()


# ── Campaign management mutations (Phase 3b — all MFA-gated) ──────────────────
# Member add/remove, system change, character create/assign/delete. The
# upload-bearing surfaces (maps, thumbnails) are intentionally NOT here —
# the Center has no /static mount, so the upload target needs design (filed
# as the remainder of Phase 3b). Every mutation runs through
# _destructive_gate (admin-tools + MFA) and is audited; on success it
# redirects back to the campaign detail page.

def _campaign_redirect(campaign_id: int, *, done: str = "", err: str = "") -> RedirectResponse:
    q = f"?done={quote(done)}" if done else (f"?err={quote(err)}" if err else "")
    return RedirectResponse(f"/campaigns/{campaign_id}{q}", status_code=303)


@app.post("/campaigns/{campaign_id}/storage-limit")
def admin_campaign_storage_limit(request: Request, campaign_id: int, limit_mb: str = Form("")):
    """Set/clear a campaign's aggregate storage limit (MB; blank/0 =
    unlimited). MFA-gated + audited."""
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    try:
        mb = float(limit_mb) if limit_mb.strip() else 0
    except ValueError:
        return _campaign_redirect(campaign_id, err="Invalid limit")
    limit_bytes = int(mb * 1024 * 1024) if mb > 0 else 0
    from . import campaign_admin, operator_audit
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    db = SessionLocal()
    try:
        try:
            c = campaign_admin.set_storage_limit(db, campaign_id, limit_bytes=limit_bytes)
        except campaign_admin.CampaignAdminError as exc:
            return _campaign_redirect(campaign_id, err=str(exc))
        operator_audit.record(
            "admin.campaign_storage_limit", operator=operator, target=c.name,
            request=request, notes=f"campaign:{campaign_id} limit_bytes={limit_bytes or 'unlimited'}",
        )
        return _campaign_redirect(
            campaign_id, done=f"storage limit {f'{mb:g} MB' if limit_bytes else 'cleared'}")
    finally:
        db.close()


# Map uploads (Phase 3b). The Admin Center shares the app's uploads volume
# (docker-compose: uploads_data RW) mounted at the same in-image path, so a
# file written here is served by the APP at /static/uploads/maps/<name>.
_UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "static" / "uploads"
_MAP_DIR = _UPLOAD_ROOT / "maps"
_ALLOWED_IMG_TYPES = {
    "image/png", "image/jpeg", "image/webp", "image/gif", "video/webm", "video/mp4",
}
_MAX_MAP_BYTES = 80 * 1024 * 1024


@app.post("/campaigns/{campaign_id}/members/add")
def admin_campaign_member_add(request: Request, campaign_id: int, user_id: int = Form(...)):
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    from . import campaign_admin, operator_audit
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    db = SessionLocal()
    try:
        try:
            u = campaign_admin.add_member(db, campaign_id, user_id=user_id)
        except campaign_admin.CampaignAdminError as exc:
            return _campaign_redirect(campaign_id, err=str(exc))
        operator_audit.record(
            "admin.campaign_member_add", operator=operator, target=u.email,
            request=request, notes=f"campaign:{campaign_id}",
        )
        return _campaign_redirect(campaign_id, done=f"added {u.email}")
    finally:
        db.close()


@app.post("/campaigns/{campaign_id}/members/remove")
def admin_campaign_member_remove(request: Request, campaign_id: int, user_id: int = Form(...)):
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    from . import campaign_admin, operator_audit
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    db = SessionLocal()
    try:
        target = campaign_admin.remove_member(db, campaign_id, user_id=user_id)
        operator_audit.record(
            "admin.campaign_member_remove", operator=operator, target=target,
            request=request, notes=f"campaign:{campaign_id}",
        )
        return _campaign_redirect(campaign_id, done=f"removed {target}")
    finally:
        db.close()


@app.post("/campaigns/{campaign_id}/system")
def admin_campaign_system(request: Request, campaign_id: int, game_system: str = Form(...)):
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    from . import campaign_admin, operator_audit
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    db = SessionLocal()
    try:
        try:
            key = campaign_admin.set_system(db, campaign_id, game_system=game_system)
        except campaign_admin.CampaignAdminError as exc:
            return _campaign_redirect(campaign_id, err=str(exc))
        operator_audit.record(
            "admin.campaign_system", operator=operator, target=key,
            request=request, notes=f"campaign:{campaign_id}",
        )
        return _campaign_redirect(campaign_id, done=f"system set to {key}")
    finally:
        db.close()


@app.post("/campaigns/{campaign_id}/characters/create")
def admin_campaign_character_create(
    request: Request, campaign_id: int,
    name: str = Form(...), owner_user_id: str = Form(""),
):
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    from . import campaign_admin, operator_audit
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    owner = int(owner_user_id) if owner_user_id.strip().isdigit() else None
    db = SessionLocal()
    try:
        try:
            char = campaign_admin.create_character(
                db, campaign_id, name=name, owner_user_id=owner,
            )
        except campaign_admin.CampaignAdminError as exc:
            return _campaign_redirect(campaign_id, err=str(exc))
        operator_audit.record(
            "admin.campaign_character_create", operator=operator, target=char.name,
            request=request, notes=f"campaign:{campaign_id}",
        )
        return _campaign_redirect(campaign_id, done=f"created character {char.name}")
    finally:
        db.close()


@app.post("/campaigns/{campaign_id}/characters/{char_id}/assign")
def admin_campaign_character_assign(
    request: Request, campaign_id: int, char_id: int,
    owner_user_id: str = Form(""),
):
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    from . import campaign_admin, operator_audit
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    owner = int(owner_user_id) if owner_user_id.strip().isdigit() else None
    db = SessionLocal()
    try:
        try:
            char = campaign_admin.assign_character(
                db, campaign_id, char_id, owner_user_id=owner,
            )
        except campaign_admin.CampaignAdminError as exc:
            return _campaign_redirect(campaign_id, err=str(exc))
        operator_audit.record(
            "admin.campaign_character_assign", operator=operator, target=char.name,
            request=request, notes=f"campaign:{campaign_id} owner={char.owner_user_id}",
        )
        return _campaign_redirect(campaign_id, done=f"reassigned {char.name}")
    finally:
        db.close()


@app.post("/campaigns/{campaign_id}/characters/{char_id}/delete")
def admin_campaign_character_delete(request: Request, campaign_id: int, char_id: int):
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    from . import campaign_admin, operator_audit
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    db = SessionLocal()
    try:
        try:
            name = campaign_admin.delete_character(db, campaign_id, char_id)
        except campaign_admin.CampaignAdminError as exc:
            return _campaign_redirect(campaign_id, err=str(exc))
        operator_audit.record(
            "admin.campaign_character_delete", operator=operator, target=name,
            request=request, notes=f"campaign:{campaign_id}",
        )
        return _campaign_redirect(campaign_id, done=f"deleted character {name}")
    finally:
        db.close()


@app.post("/campaigns/{campaign_id}/maps")
async def admin_campaign_map_upload(
    request: Request, campaign_id: int,
    name: str = Form("Map"),
    grid_type: str = Form("square"),
    grid_size_px: int = Form(70),
    width_px: int = Form(2000),
    height_px: int = Form(1500),
    image: UploadFile = File(None),
):
    """Upload a battle map to a campaign. MFA-gated + audited. The file is
    written to the shared uploads volume (served by the app at
    /static/uploads/maps/...); dimensions are auto-detected from the image
    when possible. Mirrors the in-app admin upload."""
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    import uuid
    image_url = None
    if image is not None and image.filename:
        if image.content_type not in _ALLOWED_IMG_TYPES:
            return _campaign_redirect(campaign_id, err="Unsupported image type")
        data = await image.read()
        if len(data) > _MAX_MAP_BYTES:
            return _campaign_redirect(campaign_id, err="Map image too large (>80 MB)")
        from ..storage_quota import check_quota
        from ..database import SessionLocal as _SL
        _qdb = _SL()
        try:
            _q = check_quota(_qdb, campaign_id, len(data))
        finally:
            _qdb.close()
        if _q:
            return _campaign_redirect(campaign_id, err=_q)
        # Validate the extension (not just the spoofable Content-Type) so a
        # filename like x.html can't be written + served as text/html → XSS.
        # v2.599.4 — mirrors app/upload_safety.py (redirect-style errors here).
        from ..upload_safety import IMAGE_VIDEO_EXTS
        ext = Path(image.filename or "").suffix.lower() or ".png"
        if ext not in IMAGE_VIDEO_EXTS:
            return _campaign_redirect(campaign_id, err="Unsupported image type")
        fname = f"{uuid.uuid4().hex}{ext}"
        try:
            _MAP_DIR.mkdir(parents=True, exist_ok=True)
            (_MAP_DIR / fname).write_bytes(data)
        except OSError as exc:
            log.exception("admin-center map upload write failed")
            return _campaign_redirect(campaign_id, err=f"Could not save image: {exc}")
        image_url = f"/static/uploads/maps/{fname}"
        if image.content_type and image.content_type.startswith("image/"):
            try:
                import io as _io

                from PIL import Image as _PILImage
                with _PILImage.open(_io.BytesIO(data)) as _img:
                    width_px, height_px = _img.size
            except Exception:  # noqa: BLE001 — keep the form-provided dims
                pass
    from . import campaign_admin, operator_audit
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    db = SessionLocal()
    try:
        try:
            m = campaign_admin.create_map(
                db, campaign_id, name=name, image_url=image_url,
                grid_type=grid_type, grid_size_px=grid_size_px,
                width_px=width_px, height_px=height_px,
            )
        except campaign_admin.CampaignAdminError as exc:
            return _campaign_redirect(campaign_id, err=str(exc))
        operator_audit.record(
            "admin.campaign_map_upload", operator=operator, target=m.name,
            request=request, notes=f"campaign:{campaign_id} map:{m.id}",
        )
        return _campaign_redirect(campaign_id, done=f"uploaded map {m.name}")
    finally:
        db.close()


@app.post("/campaigns/{campaign_id}/maps/{map_id}/activate")
def admin_campaign_map_activate(request: Request, campaign_id: int, map_id: int):
    """Set the campaign's active map. MFA-gated + audited."""
    blocked = _destructive_gate(request)
    if blocked is not None:
        return blocked
    from . import campaign_admin, operator_audit
    from ..database import SessionLocal
    operator = request.session.get("admin_user", "?")
    db = SessionLocal()
    try:
        try:
            m = campaign_admin.activate_map(db, campaign_id, map_id)
        except campaign_admin.CampaignAdminError as exc:
            return _campaign_redirect(campaign_id, err=str(exc))
        operator_audit.record(
            "admin.campaign_map_activate", operator=operator, target=m.name,
            request=request, notes=f"campaign:{campaign_id} map:{m.id}",
        )
        return _campaign_redirect(campaign_id, done=f"activated map {m.name}")
    finally:
        db.close()
