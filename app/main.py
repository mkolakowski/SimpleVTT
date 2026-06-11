"""SimpleVTT FastAPI application entry point."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .auth import register_oauth
from .config import get_settings
from .database import init_db, record_schema_version
from .routes import (
    admin_routes,
    audio_routes,
    auth_routes,
    homebrew_routes,
    tabletop_routes,
    user_routes,
    wiki_routes,
)
from .version import APP_VERSION, SCHEMA_VERSION

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("simplevtt")

settings = get_settings()
app = FastAPI(title="SimpleVTT", version=APP_VERSION)

app.add_middleware(SessionMiddleware, secret_key=settings.app.secret_key, https_only=False)

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

    if exc.status_code == 401 and exc.detail == "Login required" and wants_html:
        next_path = request.url.path
        if request.url.query:
            next_path += "?" + request.url.query
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
    return {"ok": True, "app_version": APP_VERSION, "schema_version": SCHEMA_VERSION}


@app.get("/version")
def version():
    return {"app_version": APP_VERSION, "schema_version": SCHEMA_VERSION}
