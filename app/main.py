"""SimpleVTT FastAPI application entry point."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
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


@app.on_event("startup")
async def on_startup() -> None:
    log.info("SimpleVTT %s (schema v%d) starting...", APP_VERSION, SCHEMA_VERSION)
    log.info("Initializing database (create_all)...")
    init_db()
    record_schema_version(SCHEMA_VERSION)
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
