"""Configuration loader.

All settings come from environment variables. In Docker, these are loaded
from .env via docker-compose. In local development, export them in your
shell or use a tool like direnv.

See .env.example for the full list of variables and their defaults.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import BaseModel, Field


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: Optional[List[str]] = None) -> List[str]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return list(default or [])
    return [p.strip() for p in raw.split(",") if p.strip()]


class AppSection(BaseModel):
    secret_key: str = "change-me"
    base_url: str = "http://localhost:8013"
    allow_local_registration: bool = True


class GoogleSSO(BaseModel):
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""


class Settings(BaseModel):
    app: AppSection = Field(default_factory=AppSection)
    admins: List[str] = Field(default_factory=list)
    google_sso: GoogleSSO = Field(default_factory=GoogleSSO)
    character_templates: List[str] = Field(
        default_factory=lambda: ["generic", "dnd5e"]
    )
    default_theme: str = "dark"

    # Demo mode (v2.3.0). See docs/plans/demo-mode.md.
    # When ``demo_mode`` is true, the lifespan handler boots a background
    # task that resets a deterministic sample dataset on a fixed interval,
    # letting a single public URL hand out clean demo instances. NEVER
    # enable this on a production deploy — it surgically wipes any data
    # tagged with demo emails/slugs every interval.
    demo_mode: bool = False
    demo_reset_interval_minutes: int = 60   # clamped to [5, 1440] at boot
    demo_reset_on_boot: bool = True
    demo_credentials_visible: bool = True   # show login creds on /login

    # Derived/runtime settings
    database_url: str = ""

    def is_admin_email(self, email: str) -> bool:
        if not email:
            return False
        norm = email.strip().lower()
        return any(a.strip().lower() == norm for a in self.admins)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings(
        app=AppSection(
            secret_key=os.environ.get("APP_SECRET_KEY", "change-me"),
            base_url=os.environ.get("APP_BASE_URL", "http://localhost:8013"),
            allow_local_registration=_env_bool("APP_ALLOW_LOCAL_REGISTRATION", True),
        ),
        admins=_env_list("ADMINS"),
        google_sso=GoogleSSO(
            enabled=_env_bool("GOOGLE_SSO_ENABLED", False),
            client_id=os.environ.get("GOOGLE_SSO_CLIENT_ID", ""),
            client_secret=os.environ.get("GOOGLE_SSO_CLIENT_SECRET", ""),
        ),
        character_templates=_env_list(
            "CHARACTER_TEMPLATES", ["generic", "dnd5e"]
        ),
        default_theme=os.environ.get("APP_DEFAULT_THEME", "dark"),
        demo_mode=_env_bool("DEMO_MODE", False),
        demo_reset_interval_minutes=max(5, min(1440, int(os.environ.get("DEMO_RESET_INTERVAL_MINUTES") or 60))),
        demo_reset_on_boot=_env_bool("DEMO_RESET_ON_BOOT", True),
        demo_credentials_visible=_env_bool("DEMO_CREDENTIALS_VISIBLE", True),
    )

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        # Sensible local fallback for non-Docker dev runs.
        db_url = "sqlite:///./simplevtt.db"
    settings.database_url = db_url

    return settings
