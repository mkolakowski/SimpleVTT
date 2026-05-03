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
from .routes import admin_routes, audio_routes, auth_routes, tabletop_routes, user_routes
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
app.include_router(audio_routes.router)
app.include_router(user_routes.router)


@app.on_event("startup")
def on_startup() -> None:
    log.info("SimpleVTT %s (schema v%d) starting...", APP_VERSION, SCHEMA_VERSION)
    log.info("Initializing database (create_all)...")
    init_db()
    record_schema_version(SCHEMA_VERSION)
    if settings.admins:
        log.info("Admins from env: %s", ", ".join(settings.admins))
    else:
        log.warning("No admins configured. Set ADMINS in .env (comma-separated emails).")


@app.get("/healthz")
def healthz():
    return {"ok": True, "app_version": APP_VERSION, "schema_version": SCHEMA_VERSION}


@app.get("/version")
def version():
    return {"app_version": APP_VERSION, "schema_version": SCHEMA_VERSION}
