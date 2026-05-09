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

    # ---- Schema v8 (0.9.0): Token.controller_user_id ----
    tok_cols = _column_names("tokens")
    with engine.begin() as conn:
        if tok_cols and "controller_user_id" not in tok_cols:
            conn.execute(text("ALTER TABLE tokens ADD COLUMN controller_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL"))

    # ---- Schema v7 (0.8.0): PlaylistTrack audio metadata columns ----
    track_cols = _column_names("playlist_tracks")
    with engine.begin() as conn:
        if track_cols and "track_artist" not in track_cols:
            conn.execute(text("ALTER TABLE playlist_tracks ADD COLUMN track_artist VARCHAR(200)"))
        if track_cols and "track_album" not in track_cols:
            conn.execute(text("ALTER TABLE playlist_tracks ADD COLUMN track_album VARCHAR(200)"))
        if track_cols and "track_genre" not in track_cols:
            conn.execute(text("ALTER TABLE playlist_tracks ADD COLUMN track_genre VARCHAR(100)"))
        if track_cols and "track_year" not in track_cols:
            conn.execute(text("ALTER TABLE playlist_tracks ADD COLUMN track_year VARCHAR(4)"))

    # ---- Schema v9 (0.9.0): Playlist.category + user_audio_category_prefs table ----
    pl_cols = _column_names("playlists")
    with engine.begin() as conn:
        if pl_cols and "category" not in pl_cols:
            conn.execute(text("ALTER TABLE playlists ADD COLUMN category VARCHAR(20) NOT NULL DEFAULT 'music'"))
    # Use SQLAlchemy model to create the table so dialect differences
    # (AUTOINCREMENT vs SERIAL) are handled automatically.
    from .models import UserAudioCategoryPref
    UserAudioCategoryPref.__table__.create(bind=engine, checkfirst=True)

    # ---- Schema v10 (0.10.0): token_templates table + Token.token_template_id ----
    from .models import TokenTemplate
    TokenTemplate.__table__.create(bind=engine, checkfirst=True)
    tok_cols2 = _column_names("tokens")
    with engine.begin() as conn:
        if tok_cols2 and "token_template_id" not in tok_cols2:
            conn.execute(text("ALTER TABLE tokens ADD COLUMN token_template_id INTEGER REFERENCES token_templates(id) ON DELETE SET NULL"))

    # ---- Schema v11 (0.11.0): characters.campaign_id nullable (standalone characters) ----
    _make_character_campaign_nullable(inspector)

    # ---- Schema v12 (0.12.0): users.theme preference ----
    user_cols = _column_names("users")
    with engine.begin() as conn:
        if user_cols and "theme" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN theme VARCHAR(20) NOT NULL DEFAULT 'dark'"))

    # ---- Schema v13 (0.13.0): member roll-log colors ----
    mem_cols_v13 = _column_names("campaign_memberships")
    with engine.begin() as conn:
        if mem_cols_v13 and "color" not in mem_cols_v13:
            conn.execute(text("ALTER TABLE campaign_memberships ADD COLUMN color VARCHAR(20)"))
    camp_cols_v13 = _column_names("campaigns")
    with engine.begin() as conn:
        if camp_cols_v13 and "gm_color" not in camp_cols_v13:
            conn.execute(text("ALTER TABLE campaigns ADD COLUMN gm_color VARCHAR(20)"))

    # ---- Schema v14 (0.14.0): character roll-log color ----
    char_cols_v14 = _column_names("characters")
    with engine.begin() as conn:
        if char_cols_v14 and "color" not in char_cols_v14:
            conn.execute(text("ALTER TABLE characters ADD COLUMN color VARCHAR(20)"))

    # ---- Schema v15 (0.15.0): campaign GM tab tint color ----
    camp_cols_v15 = _column_names("campaigns")
    with engine.begin() as conn:
        if camp_cols_v15 and "gm_tab_color" not in camp_cols_v15:
            conn.execute(text("ALTER TABLE campaigns ADD COLUMN gm_tab_color VARCHAR(20)"))

    # ---- Schema v16 (0.16.0): user tab tint colors ----
    user_cols_v16 = _column_names("users")
    with engine.begin() as conn:
        if user_cols_v16 and "battle_tab_color" not in user_cols_v16:
            conn.execute(text("ALTER TABLE users ADD COLUMN battle_tab_color VARCHAR(20)"))
        if user_cols_v16 and "player_tab_color" not in user_cols_v16:
            conn.execute(text("ALTER TABLE users ADD COLUMN player_tab_color VARCHAR(20)"))

    # ---- Schema v17 (0.17.0): roll_requests table ----
    from .models import RollRequest
    RollRequest.__table__.create(bind=engine, checkfirst=True)

    # ---- Schema v18 (0.18.0): concentration_effects table ----
    from .models import ConcentrationEffect
    ConcentrationEffect.__table__.create(bind=engine, checkfirst=True)

    # ---- Schema v19 (0.19.0): users.font_preference ----
    user_cols_v19 = _column_names("users")
    with engine.begin() as conn:
        if user_cols_v19 and "font_preference" not in user_cols_v19:
            conn.execute(text("ALTER TABLE users ADD COLUMN font_preference VARCHAR(30)"))

    # ---- Schema v20 (0.20.0): campaigns.font_override ----
    camp_cols_v20 = _column_names("campaigns")
    with engine.begin() as conn:
        if camp_cols_v20 and "font_override" not in camp_cols_v20:
            conn.execute(text("ALTER TABLE campaigns ADD COLUMN font_override VARCHAR(30)"))


def _make_character_campaign_nullable(inspector) -> None:
    """Make characters.campaign_id nullable so characters can exist without a campaign."""
    from sqlalchemy import text

    char_cols = inspector.get_columns("characters")
    camp_col = next((c for c in char_cols if c["name"] == "campaign_id"), None)
    if not camp_col or camp_col.get("nullable", True):
        return  # Already nullable or table doesn't exist

    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(text(
                "ALTER TABLE characters ALTER COLUMN campaign_id DROP NOT NULL"
            ))
        elif dialect == "sqlite":
            # SQLite doesn't support ALTER COLUMN — recreate the table
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            conn.execute(text("""
                CREATE TABLE characters_v11 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER REFERENCES campaigns(id) ON DELETE SET NULL,
                    owner_user_id INTEGER REFERENCES users(id),
                    name VARCHAR(120) NOT NULL,
                    template VARCHAR(40) NOT NULL DEFAULT 'generic',
                    sheet JSON,
                    portrait_url VARCHAR(500),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("INSERT INTO characters_v11 SELECT * FROM characters"))
            conn.execute(text("DROP TABLE characters"))
            conn.execute(text("ALTER TABLE characters_v11 RENAME TO characters"))
            conn.execute(text("PRAGMA foreign_keys=ON"))


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
