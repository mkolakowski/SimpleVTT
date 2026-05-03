"""SQLAlchemy engine + session setup."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_connect_args = {}
if _settings.database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(_settings.database_url, future=True, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create tables on first boot, then run lightweight inline migrations."""
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _apply_inline_migrations()


def _apply_inline_migrations() -> None:
    """Add columns introduced after schema v1 if they are not already present."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)

    def _column_names(table: str):
        try:
            return {c["name"] for c in inspector.get_columns(table)}
        except Exception:
            return set()

    # ---- Schema v2 (0.3.0): Campaign.game_system + thumbnail_url ----
    cols = _column_names("campaigns")
    with engine.begin() as conn:
        if cols and "game_system" not in cols:
            conn.execute(text("ALTER TABLE campaigns ADD COLUMN game_system VARCHAR(40) NOT NULL DEFAULT 'generic'"))
        if cols and "thumbnail_url" not in cols:
            conn.execute(text("ALTER TABLE campaigns ADD COLUMN thumbnail_url VARCHAR(500)"))

    # ---- Schema v3 (0.4.0): CampaignMembership.is_gm ----
    mem_cols = _column_names("campaign_memberships")
    with engine.begin() as conn:
        if mem_cols and "is_gm" not in mem_cols:
            conn.execute(text("ALTER TABLE campaign_memberships ADD COLUMN is_gm BOOLEAN NOT NULL DEFAULT FALSE"))

    # ---- Schema v4 (0.5.0): Campaign.now_playing_track_id + now_playing_loop ----
    cols2 = _column_names("campaigns")
    with engine.begin() as conn:
        if cols2 and "now_playing_track_id" not in cols2:
            conn.execute(text("ALTER TABLE campaigns ADD COLUMN now_playing_track_id INTEGER"))
        if cols2 and "now_playing_loop" not in cols2:
            conn.execute(text("ALTER TABLE campaigns ADD COLUMN now_playing_loop BOOLEAN NOT NULL DEFAULT TRUE"))

    # ---- Schema v5 (0.6.0): Campaign.now_playing_started_at + new user_audio_preferences table ----
    cols3 = _column_names("campaigns")
    with engine.begin() as conn:
        if cols3 and "now_playing_started_at" not in cols3:
            conn.execute(text("ALTER TABLE campaigns ADD COLUMN now_playing_started_at TIMESTAMP"))

    # ---- Schema v6 (0.7.0): Campaign.session_active + session_started_at ----
    # Existing campaigns default to session_active=False so deploying this
    # version doesn't suddenly expose any tabletops; GMs must explicitly Start.
    cols4 = _column_names("campaigns")
    with engine.begin() as conn:
        if cols4 and "session_active" not in cols4:
            conn.execute(text("ALTER TABLE campaigns ADD COLUMN session_active BOOLEAN NOT NULL DEFAULT FALSE"))
        if cols4 and "session_started_at" not in cols4:
            conn.execute(text("ALTER TABLE campaigns ADD COLUMN session_started_at TIMESTAMP"))


def record_schema_version(version: int) -> None:
    """Stamp the current schema version in a tiny tracking table."""
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        existing = conn.execute(
            text("SELECT 1 FROM schema_version WHERE version = :v"), {"v": version}
        ).first()
        if not existing:
            conn.execute(
                text("INSERT INTO schema_version (version) VALUES (:v)"), {"v": version}
            )
