"""SimpleVTT FastAPI application entry point."""
from __future__ import annotations

import logging
import os
import re
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .audit_log import audit
from .auth import register_oauth
from .config import get_settings
from .database import init_db, record_schema_version
from .routes import (
    admin_audit_routes,
    admin_routes,
    audio_routes,
    auth_routes,
    demo_magic_link_routes,
    homebrew_routes,
    notes_routes,
    session_recap_routes,
    suggestion_routes,
    tabletop_routes,
    user_routes,
    wiki_routes,
)
from .version import APP_VERSION, APP_VERSION_NAME, SCHEMA_VERSION
from .visitor_log import emit_visitor_request, visitor_request_log_enabled

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("simplevtt")

# v2.469.0 — Phase 4a of docs/plans/fail2ban-crowdsec-integration.md.
# Tee the canonical-event audit log (``simplevtt.audit``) to a file so
# the fail2ban container introduced in Phase 4b has a real tail target.
# The stdout handler from ``basicConfig`` stays attached via the
# default propagation, so ``docker compose logs app`` keeps showing
# audit lines too — this is purely additive.
#
# AUDIT_LOG_PATH=<empty>  → file handler is skipped (stdout-only).
# AUDIT_LOG_PATH=<path>   → 10 MB × 5 backup rotation.
#
# The parent directory is created on startup if missing; the named
# volume mount in docker-compose.yml owns the directory itself.
AUDIT_LOG_PATH = os.environ.get("AUDIT_LOG_PATH", "/var/log/simplevtt/audit.log").strip()
_AUDIT_LOG_ENABLED = False
if AUDIT_LOG_PATH:
    try:
        Path(AUDIT_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        _audit_handler = RotatingFileHandler(
            AUDIT_LOG_PATH, maxBytes=10 * 1024 * 1024, backupCount=5,
        )
        _audit_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
        ))
        logging.getLogger("simplevtt.audit").addHandler(_audit_handler)
        _AUDIT_LOG_ENABLED = True
        log.info(f"audit log tee enabled at {AUDIT_LOG_PATH}")
    except Exception as exc:  # noqa: BLE001
        # Defensive: a bad path or permission error must not fail
        # startup; the stdout handler still records audit events.
        log.warning(
            f"audit log file handler setup failed ({exc!r}); "
            "continuing stdout-only",
        )

settings = get_settings()
app = FastAPI(title="SimpleVTT", version=APP_VERSION)

# v2.599.7 — session cookie hardening. ``same_site="lax"`` is made explicit
# (it blocks cross-site POSTs, the classic CSRF vector). ``https_only`` (the
# Secure flag) is env-driven: default OFF so HTTP dev / the localhost harness
# still authenticate, but an HTTPS-only deployment should set
# SESSION_COOKIE_SECURE=true so the cookie is never sent over plaintext.
_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in ("1", "true", "yes", "on")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app.secret_key,
    same_site="lax",
    https_only=_COOKIE_SECURE,
)


# v2.480.0 — opt-in per-request visitor logging (TODO.md P2 follow-up
# to the v2.424.0–v2.477.0 security/audit arc). When the two-gate
# interlock in app/visitor_log.py is open (VISITOR_REQUEST_LOG_ENABLED
# + TRUSTED_PROXY_HOPS>=1), emit a ``visitor.request`` audit event for
# every HTTP request — path, method, status, response time, plus the
# ip/ua audit() extracts. DEFAULT OFF: per-request logging is high-
# volume + privacy-sensitive (see docs/wiki/privacy.md).
#
# Registered via @app.middleware AFTER SessionMiddleware so it sits
# OUTERMOST in the stack — the ``ms`` it records is the full
# request wall-time including session decode + routing, which is the
# figure an operator watching for traffic-pattern alarms wants.
@app.middleware("http")
async def _visitor_request_log_mw(request: Request, call_next):
    # Fast path: when the gate is closed (the default on every normal
    # deploy) skip the clock read + emit entirely so the middleware
    # adds ~no overhead to the hot path.
    if not visitor_request_log_enabled():
        return await call_next(request)
    start = time.perf_counter()
    response = await call_next(request)
    emit_visitor_request(
        request,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        ms=int((time.perf_counter() - start) * 1000),
    )
    return response

# v2.1035.0 — HTTP security-headers hardening. Adds the standard defensive
# response headers the security audit found missing (clickjacking, MIME-sniff,
# referrer leakage, and a Content-Security-Policy as a second line of defense
# behind the app's existing output-escaping). Registered AFTER the visitor-log
# middleware so it sits OUTERMOST and stamps the final response.
#
# The CSP intentionally allows ``'unsafe-inline'`` for script/style because the
# templates use inline event handlers + ``style=`` attributes; it still blocks
# external script origins, framing (``frame-ancestors 'none'``), plugins
# (``object-src 'none'``), and base-tag hijacking. Both the whole feature and
# the exact policy are env-overridable so an operator can relax or tighten
# without a code change. HSTS is emitted only when the deploy is HTTPS
# (``SESSION_COOKIE_SECURE=true``) so it never pins a plaintext dev box.
_SECURITY_HEADERS_ENABLED = os.getenv(
    "SECURITY_HEADERS_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
_DEFAULT_CSP = (
    "default-src 'self'; base-uri 'self'; object-src 'none'; "
    "frame-ancestors 'none'; img-src 'self' data: blob:; "
    "media-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self' data:"
)
_CONTENT_SECURITY_POLICY = os.getenv("CONTENT_SECURITY_POLICY", _DEFAULT_CSP).strip()


@app.middleware("http")
async def _security_headers_mw(request: Request, call_next):
    response = await call_next(request)
    if not _SECURITY_HEADERS_ENABLED:
        return response
    h = response.headers
    # setdefault: never clobber a header a handler set deliberately.
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if _CONTENT_SECURITY_POLICY:
        h.setdefault("Content-Security-Policy", _CONTENT_SECURITY_POLICY)
    if _COOKIE_SECURE:
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "uploads" / "maps").mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "uploads" / "tokens").mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "uploads" / "thumbnails").mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "uploads" / "audio").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

register_oauth(settings)

app.include_router(auth_routes.router)
app.include_router(tabletop_routes.router)
app.include_router(admin_routes.router)
app.include_router(homebrew_routes.router)
app.include_router(audio_routes.router)
app.include_router(user_routes.router)
app.include_router(wiki_routes.router)
app.include_router(notes_routes.router)
app.include_router(session_recap_routes.router)
app.include_router(suggestion_routes.router)

# v2.425.0 — Phase 1 of docs/plans/demo-magic-link.md. The router
# registers regardless of env-var state; every endpoint guards on
# ``magic_link_enabled()`` at request time + returns 404 when the
# gates aren't both open, so an attacker probing the path can't
# distinguish "feature exists but is off" from "feature doesn't
# exist." Defense-in-depth: ``magic_link_enabled()`` re-reads
# ``DEMO_MODE`` + ``SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED`` from
# os.environ on every call so a hot env-var flip is honored.
app.include_router(demo_magic_link_routes.router)

# v2.427.0 — Phase 1 of docs/plans/cloudflare-edge-banning.md.
# Admin-only edge-banning endpoints + the generic admin_audit_log
# table. Like demo_magic_link_routes, the router registers
# unconditionally and every endpoint guards on the per-request
# ``cloudflare.cloudflare_banning_enabled()`` predicate, returning
# 503 when the gates aren't both open.
app.include_router(admin_audit_routes.router)

# v2.49.12: TEST_MODE-only routes (e.g. dice-seed for the encounter-sim
# test suite, see docs/plans/encounter-sim-test-suite.md). Conditionally
# included so the endpoints don't exist at all in production — they 404
# before any handler runs because the router was never mounted.
_TEST_MODE = os.environ.get("TEST_MODE", "").strip().lower() in ("1", "true", "yes", "on")
if _TEST_MODE:
    from .routes import test_routes
    app.include_router(test_routes.router)
    log.warning("TEST_MODE is ENABLED — /api/test/* endpoints are live. Never set in production.")


# v2.3.28: when an expired-session HTML page load hits a route guarded by
# ``require_user``, FastAPI's default JSON response (``{"detail":"Login
# required"}``) makes the browser display raw JSON instead of bouncing
# back to the login form. Detect that specific 401 and respond with a
# 303 redirect for browser-style requests (``Accept: text/html`` and no
# ``Accept: application/json``). API / fetch callers — which always
# send ``Accept: application/json`` — still get the JSON, and the
# client-side fetch interceptor in ``base.html`` handles them by
# navigating to ``/login`` from JS. Other HTTPExceptions delegate to
# Starlette's default handler.
#
# v2.3.29: same handler also catches 404 — for logged-in HTML callers,
# redirect to ``/`` (the home / lobby) instead of showing a bare
# "Not found" JSON or browser-default 404 page. Unauthenticated 404s
# still fall through to the default handler (so they don't leak that a
# specific URL exists by behaving differently per auth state — they
# just see the same generic JSON).
# Register on Starlette's HTTPException — FastAPI's HTTPException
# inherits from it, so the handler catches BOTH explicit
# ``raise HTTPException(...)`` calls (FastAPI subclass) and Starlette's
# own routing-layer 404s for unmatched paths (which use the base
# class, not the FastAPI subclass — registering on the FastAPI class
# would miss them).
@app.exception_handler(StarletteHTTPException)
async def _auth_redirect_handler(request: Request, exc: StarletteHTTPException):
    accept = (request.headers.get("accept") or "").lower()
    wants_html = "text/html" in accept and "application/json" not in accept

    # v2.426.0 — finish the v2.424.0 fail2ban/CrowdSec Phase 1 by
    # emitting canonical audit-log lines for protected-endpoint
    # 401/403 responses. The intent is to give fail2ban / CrowdSec
    # filters a clean signal for "this IP just hit a 401 on a path
    # it isn't authenticated for" (credential-probe pattern). We
    # SKIP the emit on the legitimate browser-bounce path — when
    # an HTML request to a guarded page hits 401 + "Login required"
    # we redirect to /login below, and that flow happens every
    # time an unauthenticated user clicks any protected link, so
    # logging it as an audit event would drown the real signals.
    is_browser_bounce = (
        exc.status_code == 401
        and exc.detail == "Login required"
        and wants_html
    )
    if exc.status_code == 401 and not is_browser_bounce:
        audit(
            "api.unauthorized",
            level=logging.WARNING,
            request=request,
            path=request.url.path,
        )
    elif exc.status_code == 403:
        audit(
            "api.forbidden",
            level=logging.WARNING,
            request=request,
            path=request.url.path,
        )
    elif exc.status_code == 404:
        # v2.477.0 — Phase 5 of fail2ban-crowdsec-integration.md.
        # Emit a canonical audit event for every 404 so the new
        # ``simplevtt-scanner`` fail2ban jail can ban IPs that probe
        # many missing paths in a short window. A casual user might
        # hit 1–3 stale URLs in a browsing session; a vulnerability
        # scanner pumps out hundreds per minute against /.env,
        # /wp-admin, /admin.php, etc. The default threshold
        # (FAIL2BAN_SCANNER_MAXRETRY=10 / 5min, lowered from 20 in
        # v2.488.3) catches the latter without false-positiving the
        # former.
        #
        # We emit the path on every event so an operator inspecting
        # the audit log can distinguish scanner activity (many
        # distinct paths) from "one stale link hit 20×" (same path
        # repeated).
        audit(
            "api.not_found",
            level=logging.WARNING,
            request=request,
            path=request.url.path,
        )

    if is_browser_bounce:
        next_path = request.url.path
        if request.url.query:
            next_path += "?" + request.url.query
        # v2.785.0 — also stash the destination in the session so login
        # methods that don't round-trip the form ``next`` (demo magic-link,
        # Google SSO) can still return the user to where they were.
        try:
            request.session["login_next"] = next_path
        except (AttributeError, AssertionError):
            pass
        return RedirectResponse(
            f"/login?next={next_path}", status_code=303,
        )

    if exc.status_code == 404 and wants_html:
        # Session middleware exposes the session dict on request.session.
        # Peek for ``user_id`` (set by ``login_user`` in app/auth.py)
        # without a DB round-trip — we don't need the User row, just
        # "is anyone logged in here".
        try:
            user_id = request.session.get("user_id")
        except (AttributeError, AssertionError):
            user_id = None
        if user_id:
            # v2.785.8 — land an authenticated user who hit a dead DEEP link
            # (e.g. a map editor whose ID was regenerated by a demo reseed) on
            # the parent campaign — its ID is stable even when nested map/scene
            # IDs are not — instead of dumping them on the home page. Only for
            # paths deeper than ``/campaign/{cid}`` so a missing campaign itself
            # can't loop (it falls through to home).
            m = re.match(r"^/campaign/(\d+)/.+", request.url.path)
            if m:
                return RedirectResponse(f"/campaign/{m.group(1)}", status_code=303)
            return RedirectResponse("/", status_code=303)

    return await http_exception_handler(request, exc)


def _validate_all_local_content() -> dict[str, dict]:
    """v2.159.16 — boot-time validator for every shipped SRD content JSON.

    v2.159.23 — Phase 8q: extended from items-only to ALL nine content
    types via the existing ``content_schemas.TYPE_REGISTRY``. Walks
    ``app/data/local/dnd5e/<type>/*.json`` for each type and validates
    each file against its Pydantic schema. Filed in the v2.158.83
    retro: the Pearl ``key`` / ``id`` bug shipped silently because the
    only runtime validator was per-endpoint
    (``/api/content/items/{slug}``) — content only got checked when
    fetched. A boot-time sweep catches schema drift the moment a
    developer adds or edits any record.

    Returns ``{type: {checked: int, errors: list[{file, error}]}}``
    keyed by directory name (items / spells / feats / etc.). Callers
    decide whether to log + continue or crash. The startup hook today
    only logs — see Phase 8p notes.
    """
    import json as _json
    from .content_schemas import TYPE_REGISTRY as _TYPE_REGISTRY

    base_dir = Path(__file__).resolve().parent / "data" / "local" / "dnd5e"
    out: dict[str, dict] = {}
    for type_name, schema in _TYPE_REGISTRY.items():
        type_dir = base_dir / type_name
        errors: list[dict] = []
        checked = 0
        if type_dir.is_dir():
            for path in sorted(type_dir.glob("*.json")):
                checked += 1
                try:
                    with path.open("r", encoding="utf-8") as fh:
                        payload = _json.load(fh)
                except _json.JSONDecodeError as e:
                    errors.append({"file": path.name, "error": f"invalid JSON: {e}"})
                    continue
                except OSError as e:
                    errors.append({"file": path.name, "error": f"read error: {e}"})
                    continue
                try:
                    schema.model_validate(payload)
                except Exception as e:  # noqa: BLE001 — pydantic ValidationError or sub-class
                    errors.append({"file": path.name, "error": str(e).splitlines()[0]})
        out[type_name] = {"checked": checked, "errors": errors}
    return out


_CONTENT_VALIDATION_RESULT: dict[str, dict] = {}


@app.on_event("startup")
async def on_startup() -> None:
    log.info("SimpleVTT %s (schema v%d) starting...", APP_VERSION, SCHEMA_VERSION)
    log.info("Initializing database (create_all)...")
    init_db()
    record_schema_version(SCHEMA_VERSION)

    # v2.159.16 — sweep every shipped content JSON for schema
    # compliance. We log errors but DON'T crash — a broken record
    # still loads via ``resolve()`` at request-time and will surface
    # there too; the boot-time signal just makes the failure loud at
    # deploy time rather than waiting for a player to fetch the
    # record. v2.159.23 — Phase 8q: extended from items-only to all
    # nine content types via the TYPE_REGISTRY.
    try:
        result = _validate_all_local_content()
        _CONTENT_VALIDATION_RESULT.clear()
        _CONTENT_VALIDATION_RESULT.update(result)
        total_checked = 0
        total_errors = 0
        for type_name, payload in result.items():
            checked = int(payload.get("checked") or 0)
            errors = payload.get("errors") or []
            total_checked += checked
            total_errors += len(errors)
            if errors:
                log.error(
                    "Content validator [%s]: %d/%d failed validation:",
                    type_name, len(errors), checked,
                )
                for entry in errors:
                    log.error(
                        "  %s — %s",
                        entry.get("file"), entry.get("error"),
                    )
        if total_errors == 0:
            log.info(
                "Content validator: %d records across %d types OK.",
                total_checked, len(result),
            )
    except Exception as e:  # noqa: BLE001 — never block boot on the validator
        log.exception("Content validator crashed: %s", e)

    if settings.admins:
        log.info("Admins from env: %s", ", ".join(settings.admins))
    else:
        log.warning("No admins configured. Set ADMINS in .env (comma-separated emails).")

    # Demo mode (v2.3.0). When enabled, optionally reset on boot and
    # spawn the recurring reset scheduler. NEVER enable on production —
    # the reset surgically wipes any rows tagged with the demo emails /
    # campaign name. See docs/plans/demo-mode.md.
    if settings.demo_mode:
        log.warning(
            "DEMO_MODE is ENABLED — dataset will reset every %d minutes",
            settings.demo_reset_interval_minutes,
        )
        if settings.demo_reset_on_boot:
            try:
                from .demo_seed import reset_and_reseed
                from .database import SessionLocal as _SL
                with _SL() as db:
                    counts = reset_and_reseed(db)
                log.info("demo seed (boot): %s", counts)
            except Exception as e:  # noqa: BLE001
                log.exception("demo seed (boot) failed: %s", e)
        from .demo_scheduler import start_demo_scheduler
        start_demo_scheduler(app)

    # v2.531.0 — deploy-time Cloudflare cache purge. A fresh container
    # start means a (potentially) new APP_VERSION; if the operator has
    # opted in (SIMPLEVTT_CLOUDFLARE_CACHE_PURGE_ENABLED + the Cloudflare
    # client configured), flush the edge cache so the new version's
    # HTML/JS isn't served stale from Cloudflare (the issue behind a
    # public demo showing an old version after a deploy). Default-off and
    # best-effort — any failure is logged and never blocks boot.
    try:
        from .integrations import cloudflare as _cf
        if _cf.cloudflare_cache_purge_enabled():
            await _cf.purge_cache()
            log.info(
                "Cloudflare cache purged on boot for version %s.",
                APP_VERSION,
            )
    except Exception as e:  # noqa: BLE001 — never block boot on a purge
        log.warning("Cloudflare cache purge on boot skipped/failed: %s", e)


@app.get("/api/content-health")
def content_health():
    """v2.159.16 — public read-only mirror of the boot-time content-
    schema validator. v2.159.23 extends from items-only to a nested
    map keyed by content type. The harness asserts every type has
    empty errors on every CI run; an operator polling after a content
    drop can use it to confirm new records parse before cutting
    traffic over.

    Returns ``{<type_name>: {checked, errors}}`` for each of the nine
    content types. Top-level keys mirror ``content_schemas.TYPE_REGISTRY``
    (races / class_features / subclass_features / spells / items /
    feats / backgrounds / monsters / conditions).
    """
    return {k: dict(v) for k, v in _CONTENT_VALIDATION_RESULT.items()}


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if settings.demo_mode:
        from .demo_scheduler import stop_demo_scheduler
        stop_demo_scheduler(app)


@app.get("/healthz")
def healthz():
    # v2.474.0 — surface the running uid/user name so a harness test
    # (and operators) can verify the non-root hardening landed. On
    # a healthy v2.474.0+ deploy this reports `appuser` / a non-zero
    # uid. Posix-only path; on Windows / non-posix host these fall
    # back to None so the endpoint still responds.
    try:
        _uid = os.getuid()
    except AttributeError:
        _uid = None
    _user_name = None
    if _uid is not None:
        try:
            import pwd
            _user_name = pwd.getpwuid(_uid).pw_name
        except (KeyError, ImportError):
            _user_name = None
    return {
        "ok": True,
        "app_version": APP_VERSION,
        "schema_version": SCHEMA_VERSION,
        # v2.469.0 — Phase 4a: surface the audit-log file config so
        # the fail2ban Phase 4b smoke test can verify wiring without
        # docker-exec'ing into the container. Empty path / disabled
        # flag tells the operator the file handler isn't active.
        "audit_log_path": AUDIT_LOG_PATH,
        "audit_log_enabled": _AUDIT_LOG_ENABLED,
        # v2.474.0 — non-root hardening signal.
        "process_uid": _uid,
        "process_user": _user_name,
    }


@app.get("/version")
def version():
    # v2.776.0 — also surface the release "Fun Name" for clients/tests.
    return {
        "app_version": APP_VERSION,
        "app_version_name": APP_VERSION_NAME,
        "schema_version": SCHEMA_VERSION,
    }
