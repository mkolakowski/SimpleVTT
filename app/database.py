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

    # ---- Schema v21 (0.28.0): users.ui_scale + users.font_scale ----
    user_cols_v21 = _column_names("users")
    with engine.begin() as conn:
        if user_cols_v21 and "ui_scale" not in user_cols_v21:
            conn.execute(text("ALTER TABLE users ADD COLUMN ui_scale FLOAT NOT NULL DEFAULT 1.0"))
        if user_cols_v21 and "font_scale" not in user_cols_v21:
            conn.execute(text("ALTER TABLE users ADD COLUMN font_scale FLOAT NOT NULL DEFAULT 1.0"))

    # ---- Schema v22-v30 (0.42.0 - 0.51.0): custom_* tables ----
    # Historical: v22-v30 created the custom_subclasses, custom_classes,
    # custom_races, custom_monsters, custom_backgrounds, custom_feats tables
    # plus several ALTER COLUMN steps. v52 (below) exports all of these to
    # per-slug JSON files under the homebrew Docker volume, then DROPs every
    # table. We keep the v22-v30 schema-version stamps for upgrade-path
    # bookkeeping but no longer execute the CREATE statements: any database
    # upgrading from before v52 still has the tables (v52 exports & drops);
    # any database initialised at v2.0.0+ never needs them.

    # ---- Schema v31 (0.54.0): users.animate_gifs preference ----
    user_cols_v31 = _column_names("users")
    with engine.begin() as conn:
        if user_cols_v31 and "animate_gifs" not in user_cols_v31:
            conn.execute(text("ALTER TABLE users ADD COLUMN animate_gifs BOOLEAN NOT NULL DEFAULT TRUE"))

    # ---- Schema v32 (0.58.0): Campaign.auto_play_playlist_id + auto_play_mode ----
    # GMs can configure a playlist to start automatically when a session
    # begins. ``auto_play_mode`` is a small string ("order" / "shuffle").
    # The FK is nullable + ON DELETE SET NULL on the model side so dropping
    # the chosen playlist doesn't strand the campaign.
    camp_cols_v32 = _column_names("campaigns")
    with engine.begin() as conn:
        if camp_cols_v32 and "auto_play_playlist_id" not in camp_cols_v32:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN auto_play_playlist_id INTEGER "
                "REFERENCES playlists(id) ON DELETE SET NULL"
            ))
        if camp_cols_v32 and "auto_play_mode" not in camp_cols_v32:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN auto_play_mode VARCHAR(10) "
                "NOT NULL DEFAULT 'order'"
            ))

    # ---- Schema v33 (0.60.0): audio_play_events table ----
    # One row per audio play; finalized when the next play / stop /
    # session-end happens. Powers the "Audio history" panel on the
    # campaign settings page. See models.AudioPlayEvent for the full
    # column docs + ended_reason / source vocabularies.
    from .models import AudioPlayEvent
    AudioPlayEvent.__table__.create(bind=engine, checkfirst=True)

    # ---- Schema v34 (0.61.0): Campaign.now_playing_paused_offset_s ----
    # When non-null, audio is paused at this many seconds into the
    # current track. Lets resume reseek every client to the same
    # position via the existing time-sync mechanism.
    camp_cols_v34 = _column_names("campaigns")
    with engine.begin() as conn:
        if camp_cols_v34 and "now_playing_paused_offset_s" not in camp_cols_v34:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN now_playing_paused_offset_s FLOAT"
            ))

    # ---- Schema v35 (0.64.0): encounters table ----
    # GM-saved bundle of {map, tokens, initiative seed, optional
    # playlist} that can be reloaded at the table. Phase 1 ships the
    # table + a read-only listing UI; save / load / edit / delete land
    # in later phases. See docs/encounters-plan.md.
    from .models import Encounter
    Encounter.__table__.create(bind=engine, checkfirst=True)

    # ---- Schema v36 (0.68.0): encounters.tags ----
    # Free-form list of GM-chosen tags ("boss", "random", "set-piece")
    # for grouping + filtering in the library UI. JSON column type
    # varies by dialect (matches the pattern used by custom_classes.spell_list).
    enc_cols = _column_names("encounters")
    with engine.begin() as conn:
        if enc_cols and "tags" not in enc_cols:
            if engine.dialect.name == "postgresql":
                conn.execute(text("ALTER TABLE encounters ADD COLUMN tags JSON NOT NULL DEFAULT '[]'"))
            else:
                conn.execute(text("ALTER TABLE encounters ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'"))

    # ---- Schema v37 (0.71.0): maps.player_spawns ----
    # Per-character spawn points used by the GM's session-prep flow.
    # JSON dict keyed by character id (string) → {x, y}. Same JSON vs
    # TEXT dialect split as the other JSON columns above.
    # NOTE (v0.73.0): the feature moved onto the Encounter model; the
    # column stays for backward-compat but isn't read by the app.
    map_cols = _column_names("maps")
    with engine.begin() as conn:
        if map_cols and "player_spawns" not in map_cols:
            if engine.dialect.name == "postgresql":
                conn.execute(text("ALTER TABLE maps ADD COLUMN player_spawns JSON NOT NULL DEFAULT '{}'"))
            else:
                conn.execute(text("ALTER TABLE maps ADD COLUMN player_spawns TEXT NOT NULL DEFAULT '{}'"))

    # ---- Schema v38 (0.73.0): encounters.use_spawn_points + spawn_points ----
    # Per-encounter player starting spots. When ``use_spawn_points`` is
    # true the load flow places each player at the matching coord in
    # ``spawn_points`` (dict char_id_str → {x, y}) instead of using the
    # snapshot's saved player positions. Adds two columns; both default
    # to "no spawn-points behaviour" so existing encounters keep loading
    # exactly as they did before.
    enc_cols_v38 = _column_names("encounters")
    with engine.begin() as conn:
        if enc_cols_v38 and "use_spawn_points" not in enc_cols_v38:
            conn.execute(text(
                "ALTER TABLE encounters ADD COLUMN use_spawn_points BOOLEAN NOT NULL DEFAULT FALSE"
            ))
        if enc_cols_v38 and "spawn_points" not in enc_cols_v38:
            if engine.dialect.name == "postgresql":
                conn.execute(text("ALTER TABLE encounters ADD COLUMN spawn_points JSON NOT NULL DEFAULT '{}'"))
            else:
                conn.execute(text("ALTER TABLE encounters ADD COLUMN spawn_points TEXT NOT NULL DEFAULT '{}'"))

    # ---- Schema v39 (0.74.0): encounters.folder + campaigns.default_encounter_id ----
    # Library organisation + session-start auto-load. ``folder`` is a
    # single-level grouping string; empty = "Unfiled" in the UI.
    # ``default_encounter_id`` is the encounter the start_session flow
    # auto-loads. Both default to safe nulls so existing campaigns are
    # untouched until the GM opts in.
    enc_cols_v39 = _column_names("encounters")
    with engine.begin() as conn:
        if enc_cols_v39 and "folder" not in enc_cols_v39:
            conn.execute(text(
                "ALTER TABLE encounters ADD COLUMN folder VARCHAR(120) NOT NULL DEFAULT ''"
            ))
    camp_cols_v39 = _column_names("campaigns")
    with engine.begin() as conn:
        if camp_cols_v39 and "default_encounter_id" not in camp_cols_v39:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN default_encounter_id INTEGER "
                "REFERENCES encounters(id) ON DELETE SET NULL"
            ))

    # ---- Schema v40 (0.75.0): playlists.description + playlists.tags ----
    # Lightweight metadata for the playlist library + a short blurb the
    # tabletop GM Music panel renders next to the name. Both default to
    # safe empty values so existing playlists are untouched. Same
    # JSON/TEXT dialect split used elsewhere for JSON columns.
    pl_cols_v40 = _column_names("playlists")
    with engine.begin() as conn:
        if pl_cols_v40 and "description" not in pl_cols_v40:
            conn.execute(text(
                "ALTER TABLE playlists ADD COLUMN description VARCHAR(200) NOT NULL DEFAULT ''"
            ))
        if pl_cols_v40 and "tags" not in pl_cols_v40:
            if engine.dialect.name == "postgresql":
                conn.execute(text("ALTER TABLE playlists ADD COLUMN tags JSON NOT NULL DEFAULT '[]'"))
            else:
                conn.execute(text("ALTER TABLE playlists ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'"))

    # ---- Schema v41 (0.76.0): maps.tags ----
    # Free-form GM-side tags for the maps library. Same JSON/TEXT
    # dialect split used by the other tag columns.
    map_cols_v41 = _column_names("maps")
    with engine.begin() as conn:
        if map_cols_v41 and "tags" not in map_cols_v41:
            if engine.dialect.name == "postgresql":
                conn.execute(text("ALTER TABLE maps ADD COLUMN tags JSON NOT NULL DEFAULT '[]'"))
            else:
                conn.execute(text("ALTER TABLE maps ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'"))

    # ---- Schema v42 (0.78.0): encounters.stop_audio_on_load ----
    # Per-encounter audio behaviour when no playlist is bound. False
    # default preserves the pre-v0.78 "leave audio alone on load"
    # behaviour for every existing encounter.
    enc_cols_v42 = _column_names("encounters")
    with engine.begin() as conn:
        if enc_cols_v42 and "stop_audio_on_load" not in enc_cols_v42:
            conn.execute(text(
                "ALTER TABLE encounters ADD COLUMN stop_audio_on_load BOOLEAN NOT NULL DEFAULT FALSE"
            ))

    # ---- Schema v43 (0.81.0): users.zoom_speed ----
    # Per-user multiplier on wheel + pinch zoom sensitivity (default
    # 1.0, range [0.3, 1.5]). 1.0 preserves the pre-v0.81 feel for
    # wheel; pinch is dampened relative to the raw distance ratio so
    # iPad gestures aren't twitchy.
    user_cols_v43 = _column_names("users")
    with engine.begin() as conn:
        if user_cols_v43 and "zoom_speed" not in user_cols_v43:
            conn.execute(text("ALTER TABLE users ADD COLUMN zoom_speed FLOAT NOT NULL DEFAULT 1.0"))

    # ---- Schema v44 (0.82.0): campaigns.current_encounter_id ----
    # Tracks the encounter that's currently "running" at the table — set
    # by the encounter-load flow so the Battle drawer can surface the
    # active encounter even when the panel is collapsed. Mirrors the
    # default_encounter_id FK shape (use_alter handled at the model
    # level; nullable SET NULL on delete).
    camp_cols_v44 = _column_names("campaigns")
    with engine.begin() as conn:
        if camp_cols_v44 and "current_encounter_id" not in camp_cols_v44:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN current_encounter_id INTEGER "
                "REFERENCES encounters(id) ON DELETE SET NULL"
            ))

    # ---- Schema v45 (0.83.0): custom_races.system ----
    # First step toward multi-system support. Existing rows default to
    # "dnd5e" — the only system shipped — so this is purely additive. The
    # resolver and search endpoints will gain a system filter when a
    # second system (PF2e, CoC, …) actually exists; until then the column
    # is reserved.
    race_cols_v45 = _column_names("custom_races")
    with engine.begin() as conn:
        if race_cols_v45 and "system" not in race_cols_v45:
            conn.execute(text(
                "ALTER TABLE custom_races ADD COLUMN system VARCHAR(40) "
                "NOT NULL DEFAULT 'dnd5e'"
            ))

    # ---- Schema v49 (1.1.0): folder column on maps ----
    cols_v49 = _column_names("maps")
    if cols_v49 and "folder" not in cols_v49:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE maps ADD COLUMN folder VARCHAR(120) DEFAULT ''"))

    # ---- Schema v50 (1.2.0): thumbnail_url column on maps ----
    cols_v50 = _column_names("maps")
    if cols_v50 and "thumbnail_url" not in cols_v50:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE maps ADD COLUMN thumbnail_url VARCHAR(500)"))

    # ---- Schema v51 (1.3.0): ring_style column on characters ----
    char_cols_v51 = _column_names("characters")
    if char_cols_v51 and "ring_style" not in char_cols_v51:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE characters ADD COLUMN ring_style VARCHAR(20)"))

    # ---- Schema v48 (0.94.0): auto_play_track_id on encounters ----
    cols_v48 = _column_names("encounters")
    if cols_v48 and "auto_play_track_id" not in cols_v48:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE encounters ADD COLUMN auto_play_track_id INTEGER"
                " REFERENCES playlist_tracks(id) ON DELETE SET NULL"
            ))

    # ---- Schema v47 (0.91.0): hp_thresholds JSON column on campaigns ----
    cols_v47 = _column_names("campaigns")
    if cols_v47 and "hp_thresholds" not in cols_v47:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE campaigns ADD COLUMN hp_thresholds JSON"))

    # ---- Schema v46 (0.84.0): system column on the rest of Custom* ----
    # Extends the v45 namespacing pattern to every campaign-authored
    # content type so the data model is symmetric. Same shape on every
    # table: ``system VARCHAR(40) NOT NULL DEFAULT 'dnd5e'``. Existing
    # rows are stamped ``dnd5e`` automatically by the DEFAULT.
    for _table in (
        "custom_classes",
        "custom_subclasses",
        "custom_backgrounds",
        "custom_feats",
        "custom_monsters",
    ):
        cols_v46 = _column_names(_table)
        if cols_v46 and "system" not in cols_v46:
            with engine.begin() as conn:
                conn.execute(text(
                    f"ALTER TABLE {_table} ADD COLUMN system VARCHAR(40) "
                    "NOT NULL DEFAULT 'dnd5e'"
                ))

    # ---- Schema v52 (2.0.0): export Custom* rows to homebrew volume, drop tables ----
    # Forward-only, destructive: every row in the six ``custom_*`` tables is
    # written to per-slug JSON files under the homebrew Docker volume, then
    # the tables are DROPPED. Idempotent — once the tables are gone, this
    # block is a no-op. Operators MUST back up Postgres before upgrading;
    # see CHANGELOG.md for verification steps. The dump+drop logic lives in
    # ``app/_migrate_v52.py`` so the helpers can be unit-tested without the
    # full inline-migration framework around them.
    from ._migrate_v52 import run_v52_migration
    run_v52_migration(engine)

    # ---- Schema v53 (2.4.0): maps.show_grid overlay toggle ----
    # Per-map boolean controlling whether the tabletop client renders the
    # grid overlay. Orthogonal to ``grid_type`` — snap-to-grid token
    # placement still derives from grid_type (square / hex / none) so the
    # GM can show a map whose grid is baked into the background image
    # without doubling it up with the client-drawn overlay, while still
    # getting clean snap behaviour.
    map_cols_v53 = _column_names("maps")
    with engine.begin() as conn:
        if map_cols_v53 and "show_grid" not in map_cols_v53:
            conn.execute(text("ALTER TABLE maps ADD COLUMN show_grid BOOLEAN NOT NULL DEFAULT TRUE"))

    # ---- Schema v54 (2.5.0): campaigns.potions_as_bonus_action ----
    # Per-campaign house-rule toggle that records the GM's preference for
    # potion-action timing. Default False (RAW: drinking a potion is an
    # action). The action-economy tracker's Phase 2 will consult this
    # column when a "Use Item" button is clicked on a potion-type
    # inventory item and tag the matching economy slot accordingly.
    camp_cols_v54 = _column_names("campaigns")
    with engine.begin() as conn:
        if camp_cols_v54 and "potions_as_bonus_action" not in camp_cols_v54:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN potions_as_bonus_action "
                "BOOLEAN NOT NULL DEFAULT FALSE"
            ))

    # ---- Schema v55 (2.8.0): campaigns.strict_action_economy ----
    # Per-campaign toggle that hard-blocks player over-budget rolls
    # through the Phase 4 modal. When True, the 409 over_budget response
    # carries strict:true and the Layer B modal hides its Confirm
    # button — only the GM can clear a spent chip (shift+click on the
    # init tracker). The move endpoint also broadcasts a feature_used
    # audit entry on the first drag that pushes a combatant past speed.
    camp_cols_v55 = _column_names("campaigns")
    with engine.begin() as conn:
        if camp_cols_v55 and "strict_action_economy" not in camp_cols_v55:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN strict_action_economy "
                "BOOLEAN NOT NULL DEFAULT FALSE"
            ))


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
