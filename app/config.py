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
    default_theme: str = "sepia"

    # App-wide role caps (v2.584.0). See docs/plans/app-wide-roles-and-storage.md.
    # Players (non-GM, non-admin) may own at most ``player_character_limit``
    # characters; GMs (non-admin) may own at most ``gm_campaign_limit``
    # campaigns. Admins are uncapped. 0 = unlimited.
    player_character_limit: int = 5
    gm_campaign_limit: int = 10

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

    # Lock down user file uploads on a public demo (v2.1034.0). Only takes
    # effect when ``demo_mode`` is ALSO true — a normal deploy is never
    # affected. When both are true, every user-facing upload endpoint
    # (token/portrait/template/map/handout/encounter-background images, audio
    # tracks, and character/campaign import) returns 403 so anonymous demo
    # visitors can't push arbitrary files into the shared uploads volume.
    # Defaults true so a public demo is locked down out of the box; set
    # ``DEMO_DISABLE_UPLOADS=false`` to re-enable uploads on a demo instance
    # you control. See docs/plans/demo-mode.md.
    demo_disable_uploads: bool = True

    # Version-number display (v2.776.0). Operator toggles for the masthead /
    # footer version stamp. All default true so a fresh deploy looks the same
    # as before. ``show_version`` hides the stamp entirely;
    # ``version_link_changelog`` makes it link to the wiki changelog (current
    # release is always at the top); ``show_version_name`` appends the release
    # "Fun Name" (``APP_VERSION_NAME``).
    show_version: bool = True
    version_link_changelog: bool = True
    show_version_name: bool = True

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
        default_theme=os.environ.get("APP_DEFAULT_THEME", "sepia"),
        player_character_limit=max(0, int(os.environ.get("PLAYER_CHARACTER_LIMIT") or 5)),
        gm_campaign_limit=max(0, int(os.environ.get("GM_CAMPAIGN_LIMIT") or 10)),
        demo_mode=_env_bool("DEMO_MODE", False),
        demo_reset_interval_minutes=max(5, min(1440, int(os.environ.get("DEMO_RESET_INTERVAL_MINUTES") or 60))),
        demo_reset_on_boot=_env_bool("DEMO_RESET_ON_BOOT", True),
        demo_credentials_visible=_env_bool("DEMO_CREDENTIALS_VISIBLE", True),
        demo_disable_uploads=_env_bool("DEMO_DISABLE_UPLOADS", True),
        show_version=_env_bool("SHOW_VERSION", True),
        version_link_changelog=_env_bool("VERSION_LINK_CHANGELOG", True),
        show_version_name=_env_bool("SHOW_VERSION_NAME", True),
    )

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        # Sensible local fallback for non-Docker dev runs.
        db_url = "sqlite:///./simplevtt.db"
    settings.database_url = db_url

    return settings
