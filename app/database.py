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

    # ---- Schema v56 (2.24.0): campaigns.auto_apply_damage ----
    # Phase T.2 toggle. When True, /attack auto-applies HP changes to
    # the targeted creature (resistance via Phase B's _resistance_halve
    # halves correctly; crit doubles damage dice). Defaults False so
    # existing tables aren't surprised by HP mutations — GM opts in via
    # the campaign settings page when ready.
    camp_cols_v56 = _column_names("campaigns")
    with engine.begin() as conn:
        if camp_cols_v56 and "auto_apply_damage" not in camp_cols_v56:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN auto_apply_damage "
                "BOOLEAN NOT NULL DEFAULT FALSE"
            ))

    # ---- Schema v57 (2.49.244): users.roll_log_position ----
    # Per-user ergonomic preference for where the Roll Log drawer
    # renders on the tabletop. "right" (default) keeps it stacked with
    # the other drawer tabs in the shared right-side sidebar. "left"
    # pulls roll log into its own independent left-side sidebar so the
    # player can view it alongside Battle / Characters / Settings on
    # the right. Persisted on the User row alongside theme /
    # font_preference / battle_tab_color / player_tab_color.
    user_cols_v57 = _column_names("users")
    with engine.begin() as conn:
        if user_cols_v57 and "roll_log_position" not in user_cols_v57:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN roll_log_position "
                "VARCHAR(10) NOT NULL DEFAULT 'right'"
            ))

    # ---- Schema v58 (2.62.0): users.glass_alpha ----
    # Per-user transparency / glass-effect strength for the tabletop's
    # frosted-card surfaces. Integer percent 1-100; default 42 to
    # match the v2.50.3 baseline. Body element renders
    # ``--glass-alpha: Npx`` so all 9 sites in tabletop.html using
    # ``color-mix(in srgb, var(--bg) 42%, transparent)`` now read
    # ``var(--bg) var(--glass-alpha, 42%)``.
    user_cols_v58 = _column_names("users")
    with engine.begin() as conn:
        if user_cols_v58 and "glass_alpha" not in user_cols_v58:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN glass_alpha "
                "INTEGER NOT NULL DEFAULT 42"
            ))

    # ---- Schema v59 (2.64.0): tokens.hidden_from_user_ids ----
    # Per-user fog-of-war list on each token. JSON array of user_ids
    # who can't see this token. Empty default — token visible to all
    # players. GM viewport always sees every token regardless.
    # Distinct from the legacy `is_hidden` boolean (which hides from
    # ALL non-GM users); the new field is additive — specific users
    # may be hidden from while others can still see.
    token_cols_v59 = _column_names("tokens")
    with engine.begin() as conn:
        if token_cols_v59 and "hidden_from_user_ids" not in token_cols_v59:
            dialect = engine.dialect.name
            if dialect == "postgresql":
                conn.execute(text(
                    "ALTER TABLE tokens ADD COLUMN hidden_from_user_ids "
                    "JSONB NOT NULL DEFAULT '[]'::jsonb"
                ))
            else:
                # SQLite stores JSON as TEXT internally; column type
                # JSON is accepted but check-constraints differ.
                conn.execute(text(
                    "ALTER TABLE tokens ADD COLUMN hidden_from_user_ids "
                    "JSON NOT NULL DEFAULT '[]'"
                ))

    # ---- Schema v60 (2.67.0): users.reaction_prompt_mode ----
    # Per-user setting controlling whether reaction prompts surface as
    # a popup toast, a roll-log entry only, or are suppressed entirely.
    # Default "popup" matches the v2.67.0 Phase 1 UX. Values:
    #   "popup"          — popup + roll-log (default)
    #   "roll_log_only"  — roll-log entry only (no popup)
    #   "off"            — no reaction prompts (legacy chip-click only)
    # See docs/plans/reactions-automation.md.
    user_cols_v60 = _column_names("users")
    with engine.begin() as conn:
        if user_cols_v60 and "reaction_prompt_mode" not in user_cols_v60:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN reaction_prompt_mode "
                "VARCHAR(16) NOT NULL DEFAULT 'popup'"
            ))

    # ---- Schema v61 (2.84.0): users.sepia_texture ----
    # Per-user toggle for the sepia theme's wood-grain background
    # pattern. v2.85.0 flipped the default from TRUE → FALSE so the
    # sepia theme renders the flat solid sepia color out of the box;
    # the textured look is opt-in via /settings. Body element renders
    # the `sepia-texture-on` CSS class when the user's `sepia_texture`
    # is true AND the active theme is "sepia"; the matching CSS
    # selector layers an inline-SVG wood-grain on top of the existing
    # --bg color.
    user_cols_v61 = _column_names("users")
    with engine.begin() as conn:
        if user_cols_v61 and "sepia_texture" not in user_cols_v61:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN sepia_texture "
                "BOOLEAN NOT NULL DEFAULT FALSE"
            ))

    # ---- Schema v64 (2.87.0): campaign default background ----
    # GMs can set a campaign-wide default background that's used
    # when an encounter loads without its own background_url. See
    # models.Campaign.default_background_url for the contract. Null
    # default keeps existing campaigns at "no default" semantics —
    # encounters without a bg fall back to NULL (no background), same
    # behaviour as before v2.87.0.
    camp_cols_v64 = _column_names("campaigns")
    with engine.begin() as conn:
        if camp_cols_v64 and "default_background_url" not in camp_cols_v64:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN default_background_url "
                "VARCHAR(500)"
            ))

    # ---- Schema v65 (2.99.52): Token.team ----
    # plan-movement-oa-flow Phase 1 — adds a faction tag
    # ("hero" | "villain" | "neutral") used by
    # `_check_opportunity_attack_triggers` to skip same-team OAs.
    # Existing rows default to "neutral" so pre-Phase-1 campaigns
    # see no behavior change until the GM opts a token into the
    # filter via the Token Management UI (Phase 2). The filter only
    # fires when BOTH mover and watcher are non-neutral and match.
    tok_cols_v65 = _column_names("tokens")
    with engine.begin() as conn:
        if tok_cols_v65 and "team" not in tok_cols_v65:
            conn.execute(text(
                "ALTER TABLE tokens ADD COLUMN team "
                "VARCHAR(16) NOT NULL DEFAULT 'neutral'"
            ))

    # ---- Schema v66 (2.99.168): Token.disguise ----
    # Token-disguise primitive for Wild Shape / Polymorph (and
    # future Disguise Self / Alter Self / True Polymorph). When a
    # form is applied, the original token's label + size are
    # snapshotted into the `disguise.original` sub-dict; the live
    # token fields are replaced with the new form's values. /revert
    # restores the originals and clears the disguise. JSON nullable
    # so existing rows default to no-disguise without a DDL trip.
    tok_cols_v66 = _column_names("tokens")
    with engine.begin() as conn:
        if tok_cols_v66 and "disguise" not in tok_cols_v66:
            conn.execute(text(
                "ALTER TABLE tokens ADD COLUMN disguise JSON"
            ))

    # ---- Schema v63 (2.86.0): encounter backgrounds ----
    # Two new columns enable the encounter-background feature: a
    # fullscreen fixed-position image/video layer BEHIND the battle
    # map that stays still while the map pans/zooms. See models.py
    # for the full rendering contract.
    #   - encounters.background_url — per-encounter source of truth
    #   - campaigns.active_background_url — currently-displayed handle
    # Both are nullable VARCHAR(500), defaulting NULL (no background).
    # The encounter-load flow (_perform_encounter_load) copies
    # encounter.background_url → campaign.active_background_url and
    # broadcasts a background_change message.
    enc_cols_v63 = _column_names("encounters")
    camp_cols_v63 = _column_names("campaigns")
    with engine.begin() as conn:
        if enc_cols_v63 and "background_url" not in enc_cols_v63:
            conn.execute(text(
                "ALTER TABLE encounters ADD COLUMN background_url "
                "VARCHAR(500)"
            ))
        if camp_cols_v63 and "active_background_url" not in camp_cols_v63:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN active_background_url "
                "VARCHAR(500)"
            ))

    # ---- Schema v62 (2.85.0): flip sepia_texture default off ----
    # v2.84.0 shipped with DEFAULT TRUE so every user landed on the
    # textured look without opting in. v2.85.0 reverses that: the
    # textured background is opt-in. Two parts here:
    #   1. ALTER the column DEFAULT to FALSE so fresh INSERTs that
    #      omit the field land on the new default.
    #   2. UPDATE every existing row currently sitting at TRUE back
    #      to FALSE — anyone who landed on TRUE via v2.84.0's
    #      default never made an active choice, so resetting to the
    #      new default is the user-respecting move. Users who
    #      actually want the texture can re-enable via /settings.
    # Gated on the `schema_version` tracking table so the one-shot
    # UPDATE runs exactly once: on subsequent boots v62 is already
    # stamped, so we skip both the ALTER and the UPDATE. This means
    # users who toggle the texture back ON via /settings won't have
    # it flipped off again on the next container restart.
    user_cols_v62 = _column_names("users")
    if user_cols_v62 and "sepia_texture" in user_cols_v62:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            already = conn.execute(
                text("SELECT 1 FROM schema_version WHERE version = 62")
            ).first()
            if not already:
                conn.execute(text(
                    "ALTER TABLE users ALTER COLUMN sepia_texture "
                    "SET DEFAULT FALSE"
                ))
                conn.execute(text(
                    "UPDATE users SET sepia_texture = FALSE "
                    "WHERE sepia_texture = TRUE"
                ))

    # ---- Schema v67 (2.101.0): persist the battle hub ----
    # New `battles` table — one row per campaign holding the active
    # battle/initiative-tracker state as JSON, keyed on campaign_id.
    # `Base.metadata.create_all` (run just before this function in
    # init_db) already creates the table on both fresh and existing
    # DBs, so this block is a belt-and-suspenders CREATE TABLE IF NOT
    # EXISTS that also documents the schema bump. The in-memory hub
    # (`realtime.CampaignHub`) write-through-persists here so the
    # server's authoritative battle survives a restart / demo reseed.
    # See app/models.py::Battle for the full rationale.
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS battles ("
            "campaign_id INTEGER PRIMARY KEY REFERENCES campaigns(id) "
            "ON DELETE CASCADE, "
            "state JSON, "
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))

    # ---- Schema v68 (2.102.0): campaign movement lock ----
    # Two booleans on campaigns:
    #   - movement_locked        — LIVE state; /token/move rejects non-GM
    #                              drags with 409 `movement_locked` when True.
    #   - movement_lock_default  — campaign setting seeded onto
    #                              movement_locked at encounter-load time.
    # Both NOT NULL DEFAULT FALSE so existing campaigns keep the unlocked
    # behavior until a GM opts in.
    camp_cols_v68 = _column_names("campaigns")
    with engine.begin() as conn:
        if camp_cols_v68 and "movement_locked" not in camp_cols_v68:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN movement_locked "
                "BOOLEAN NOT NULL DEFAULT FALSE"
            ))
        if camp_cols_v68 and "movement_lock_default" not in camp_cols_v68:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN movement_lock_default "
                "BOOLEAN NOT NULL DEFAULT FALSE"
            ))

    # ---- Schema v69 (2.115.0): dice_rolls.character_id ----
    # Persist the rolling character on each roll so the server-rendered
    # roll history can show the reroll button (Lucky etc.) for past
    # rolls, not just live WS ones. Nullable FK → characters (SET NULL
    # on delete); existing rows backfill to NULL (no reroll button).
    roll_cols_v69 = _column_names("dice_rolls")
    with engine.begin() as conn:
        if roll_cols_v69 and "character_id" not in roll_cols_v69:
            conn.execute(text(
                "ALTER TABLE dice_rolls ADD COLUMN character_id INTEGER "
                "REFERENCES characters(id) ON DELETE SET NULL"
            ))

    # ---- Schema v70 (2.425.0): demo_magic_links table ----
    # Phase 1 of docs/plans/demo-magic-link.md. Single-use enforcement
    # for URL-based passwordless login on the demo instance. PK = jti
    # (22-char base64url). A duplicate insert is the replay-detection
    # signal — see app/routes/demo_magic_link_routes::_consume_jti.
    # Tiny table by design; never read by anything except the consume
    # path's INSERT-or-violate. ``Base.metadata.create_all`` (earlier
    # in init_db) already creates the table; this block is a
    # belt-and-suspenders CREATE TABLE IF NOT EXISTS so the migration
    # is grep-able + documents the schema bump.
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS demo_magic_links ("
            "jti VARCHAR(40) PRIMARY KEY, "
            "sub VARCHAR(200) NOT NULL, "
            "consumed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))

    # ---- Schema v71 (2.427.0): admin_audit_log table ----
    # Phase 1 of docs/plans/cloudflare-edge-banning.md. Generic
    # admin-action audit log — Phase 1 logs cloudflare-ban /
    # cloudflare-unban; future phases (campaign-delete, user-purge,
    # demo-magic-link mint events) drop into the same schema. Queries
    # go by actor_user_id or target. ``Base.metadata.create_all``
    # already creates the table; this block is a belt-and-suspenders
    # CREATE TABLE IF NOT EXISTS + the two supporting indices.
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS admin_audit_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "actor_user_id INTEGER NOT NULL REFERENCES users(id), "
            "action VARCHAR(60) NOT NULL, "
            "target VARCHAR(200) NOT NULL, "
            "scope VARCHAR(100), "
            "cloudflare_rule_id VARCHAR(80), "
            "notes TEXT, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")" if engine.dialect.name == "sqlite" else
            "CREATE TABLE IF NOT EXISTS admin_audit_log ("
            "id BIGSERIAL PRIMARY KEY, "
            "actor_user_id BIGINT NOT NULL REFERENCES users(id), "
            "action VARCHAR(60) NOT NULL, "
            "target VARCHAR(200) NOT NULL, "
            "scope VARCHAR(100), "
            "cloudflare_rule_id VARCHAR(80), "
            "notes TEXT, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
            ")"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS admin_audit_log_actor_idx "
            "ON admin_audit_log (actor_user_id, created_at)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS admin_audit_log_target_idx "
            "ON admin_audit_log (target, created_at)"
        ))

    # ---- Schema v72 (2.554.0): campaign_notes table ----
    # Phase 1 of docs/plans/notes-and-handouts.md — GM prep notes today
    # (kind="gm_note", visibility="gm_only"); later phases reuse the
    # same table for player public notes (Phase 3) and E2E-encrypted
    # private notes (Phase 4, enc_title/enc_body opaque ciphertext).
    # ``Base.metadata.create_all`` (earlier in init_db) already creates
    # the table; this explicit create(checkfirst) covers existing DBs +
    # documents the schema bump. See models.CampaignNote.
    from .models import CampaignNote
    CampaignNote.__table__.create(bind=engine, checkfirst=True)

    # ---- Schema v73 (2.555.0): handouts table ----
    # Phase 2 of docs/plans/notes-and-handouts.md — GM-authored handouts
    # revealable to all or specific players (reveal_to JSON = "all" or a
    # user_id list). Reveal broadcasts a handout_revealed WS event scoped
    # via recipient_filter. ``Base.metadata.create_all`` creates it on
    # fresh DBs; this explicit create(checkfirst) covers existing DBs.
    from .models import Handout
    Handout.__table__.create(bind=engine, checkfirst=True)

    # ---- Schema v74 (2.557.0): note_encryption_keys table ----
    # Phase 4 of docs/plans/notes-and-handouts.md — per-user crypto
    # material (salt + KDF params + key_check) for end-to-end-encrypted
    # private notes. The server stores no passphrase, no key, and no
    # plaintext; private notes live as ciphertext in
    # campaign_notes.enc_title / enc_body. ``Base.metadata.create_all``
    # creates it on fresh DBs; this explicit create(checkfirst) covers
    # existing DBs.
    from .models import NoteEncryptionKey
    NoteEncryptionKey.__table__.create(bind=engine, checkfirst=True)

    # ---- Schema v75 (2.565.0): note_encryption_keys.recovery_wrapped_key ----
    # Optional recovery key for private notes — the note key wrapped under
    # a user-downloaded recovery key (an alternate unlock for a forgotten
    # passphrase). Nullable; existing rows default to "no recovery". The
    # server stores only the ciphertext envelope.
    nek_cols = _column_names("note_encryption_keys")
    with engine.begin() as conn:
        if nek_cols and "recovery_wrapped_key" not in nek_cols:
            conn.execute(text(
                "ALTER TABLE note_encryption_keys "
                "ADD COLUMN recovery_wrapped_key TEXT"
            ))

    # ---- Schema v76 (2.584.0): users.is_gm ----
    # App-wide GM role (may create + run campaigns). Distinct from the
    # per-campaign GM (campaigns.gm_user_id / campaign_memberships.is_gm).
    # Existing rows default to non-GM; the demo seed back-fills the demo GM.
    # See docs/plans/app-wide-roles-and-storage.md.
    user_cols = _column_names("users")
    with engine.begin() as conn:
        if user_cols and "is_gm" not in user_cols:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN is_gm BOOLEAN NOT NULL DEFAULT FALSE"
            ))

    # ---- Schema v77 (2.589.0): per-user + per-campaign storage limits ----
    # Aggregate upload-storage caps in bytes (NULL = unlimited), set in the
    # Admin Center + enforced at upload time. See
    # docs/plans/app-wide-roles-and-storage.md.
    user_cols = _column_names("users")
    camp_cols = _column_names("campaigns")
    with engine.begin() as conn:
        if user_cols and "storage_limit_bytes" not in user_cols:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN storage_limit_bytes BIGINT"
            ))
        if camp_cols and "storage_limit_bytes" not in camp_cols:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN storage_limit_bytes BIGINT"
            ))

    # ---- Schema v78 (2.603.0): campaigns.is_archived + archived_at ----
    # Soft archive for campaigns — archived campaigns drop out of the
    # active lobby sections but keep all data. Reversible (unarchive).
    # See docs/plans/campaign-pc-archive.md.
    camp_cols_v78 = _column_names("campaigns")
    with engine.begin() as conn:
        if camp_cols_v78 and "is_archived" not in camp_cols_v78:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT FALSE"
            ))
        if camp_cols_v78 and "archived_at" not in camp_cols_v78:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN archived_at TIMESTAMP"
            ))

    # ---- Schema v79 (2.604.0): characters.is_archived + archived_at ----
    # Soft retire for characters — retired characters drop out of the
    # active /characters listing but keep their full sheet + history.
    # Reversible (unretire). See docs/plans/campaign-pc-archive.md.
    char_cols_v79 = _column_names("characters")
    with engine.begin() as conn:
        if char_cols_v79 and "is_archived" not in char_cols_v79:
            conn.execute(text(
                "ALTER TABLE characters ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT FALSE"
            ))
        if char_cols_v79 and "archived_at" not in char_cols_v79:
            conn.execute(text(
                "ALTER TABLE characters ADD COLUMN archived_at TIMESTAMP"
            ))

    # ---- Schema v80 (2.606.0): users.last_login_at ----
    # Last successful login timestamp (NULL = never). Stamped in
    # auth.login_user; surfaced in the Admin Center user table.
    user_cols_v80 = _column_names("users")
    with engine.begin() as conn:
        if user_cols_v80 and "last_login_at" not in user_cols_v80:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP"
            ))

    # ---- Schema v81 (2.650.0): campaign_stat_events ----
    # The per-campaign statistics event log (one row per damage/heal/
    # cast/attack/ko event) backing the stats page. `create_all` above
    # handles fresh DBs; this checkfirst create ensures existing
    # deployments pick up the new table. See models.CampaignStatEvent +
    # docs/plans/campaign-stats.md.
    from .models import CampaignStatEvent
    CampaignStatEvent.__table__.create(bind=engine, checkfirst=True)

    # ---- Schema v82 (2.704.0): vision & light columns ----
    # Phase 0 of docs/plans/vision-and-light.md. maps.ambient_light
    # ("bright" | "dim" | "dark", default "bright" = status quo) + a
    # token-anchored light source (light_bright_ft / light_dim_ft, default
    # 0 = emits no light). All additive + default-preserving, so existing
    # maps/tokens behave exactly as before until a GM opts in.
    map_cols_v82 = _column_names("maps")
    with engine.begin() as conn:
        if map_cols_v82 and "ambient_light" not in map_cols_v82:
            conn.execute(text(
                "ALTER TABLE maps ADD COLUMN ambient_light VARCHAR(10) "
                "NOT NULL DEFAULT 'bright'"
            ))
    tok_cols_v82 = _column_names("tokens")
    with engine.begin() as conn:
        if tok_cols_v82 and "light_bright_ft" not in tok_cols_v82:
            conn.execute(text(
                "ALTER TABLE tokens ADD COLUMN light_bright_ft INTEGER "
                "NOT NULL DEFAULT 0"
            ))
        if tok_cols_v82 and "light_dim_ft" not in tok_cols_v82:
            conn.execute(text(
                "ALTER TABLE tokens ADD COLUMN light_dim_ft INTEGER "
                "NOT NULL DEFAULT 0"
            ))

    # ---- Schema v83 (2.716.0): suggestions table ----
    # User-submitted suggestions / issue reports (the in-app "Suggest /
    # Report" button), triaged in the admin portal. New table — created via
    # the model's metadata so fresh + existing deployments pick it up. See
    # models.Suggestion.
    from .models import Suggestion
    Suggestion.__table__.create(bind=engine, checkfirst=True)

    # ---- Schema v84 (2.729.0): roll_requests.initiative_combatant_id ----
    # Initiative-prompt roll requests carry the battle combatant id so the
    # responder's total is written back as that combatant's initiative. Additive
    # nullable column; existing roll-requests behave exactly as before.
    rr_cols_v84 = _column_names("roll_requests")
    with engine.begin() as conn:
        if rr_cols_v84 and "initiative_combatant_id" not in rr_cols_v84:
            conn.execute(text(
                "ALTER TABLE roll_requests ADD COLUMN "
                "initiative_combatant_id VARCHAR(64)"
            ))

    # ---- Schema v85 (2.733.0): maps.letterbox_color ----
    # Optional per-map canvas surround colour. When set (``#rrggbb``), the
    # tabletop paints the letterbox gutter + #map-pane this colour instead of
    # the default dark overlay; the GM toggle stores the map image's average
    # colour. Additive nullable column; NULL = pre-feature dark letterbox.
    maps_cols_v85 = _column_names("maps")
    with engine.begin() as conn:
        if maps_cols_v85 and "letterbox_color" not in maps_cols_v85:
            conn.execute(text(
                "ALTER TABLE maps ADD COLUMN letterbox_color VARCHAR(16)"
            ))

    # ---- Schema v86 (2.743.0): campaigns.ability_rolls_locked ----
    # GM toggle that blocks non-GM players from the sheet's 4d6 ability-score
    # roller (point-buy unaffected). Additive; default false = unlocked.
    camp_cols_v86 = _column_names("campaigns")
    with engine.begin() as conn:
        if camp_cols_v86 and "ability_rolls_locked" not in camp_cols_v86:
            conn.execute(text(
                "ALTER TABLE campaigns ADD COLUMN ability_rolls_locked "
                "BOOLEAN NOT NULL DEFAULT FALSE"
            ))

    # ---- Schema v87 (2.752.0): maps.walls ----
    # Maps 2.0 walls & doors — a JSON list of wall/door line segments stored
    # at the map level. Additive; default empty list = no walls.
    maps_cols_v87 = _column_names("maps")
    with engine.begin() as conn:
        if maps_cols_v87 and "walls" not in maps_cols_v87:
            conn.execute(text(
                "ALTER TABLE maps ADD COLUMN walls JSON NOT NULL DEFAULT '[]'"
            ))

    # ---- Schema v88 (2.756.0): maps.hotspots ----
    # Maps 2.0 clickable hotspots — a JSON list of GM-placed map markers.
    # Additive; default empty list.
    maps_cols_v88 = _column_names("maps")
    with engine.begin() as conn:
        if maps_cols_v88 and "hotspots" not in maps_cols_v88:
            conn.execute(text(
                "ALTER TABLE maps ADD COLUMN hotspots JSON NOT NULL DEFAULT '[]'"
            ))

    # ---- Schema v89 (2.761.0): encounters.linked_map_ids ----
    # Maps 2.0 multi-map encounters — a JSON list of additional map ids the
    # encounter groups for quick active-map switching. Additive; default [].
    enc_cols_v89 = _column_names("encounters")
    with engine.begin() as conn:
        if enc_cols_v89 and "linked_map_ids" not in enc_cols_v89:
            conn.execute(text(
                "ALTER TABLE encounters ADD COLUMN linked_map_ids "
                "JSON NOT NULL DEFAULT '[]'"
            ))

    # ---- Schema v90 (2.765.0): maps.lights ----
    # Maps 2.0 placeable light sources — a JSON list of bright/dim emitters.
    # Additive; default empty list.
    maps_cols_v90 = _column_names("maps")
    with engine.begin() as conn:
        if maps_cols_v90 and "lights" not in maps_cols_v90:
            conn.execute(text(
                "ALTER TABLE maps ADD COLUMN lights JSON NOT NULL DEFAULT '[]'"
            ))

    # ---- Schema v91 (2.766.0): maps.fog_enabled + maps.fog_revealed ----
    # Maps 2.0 fog of war — a per-map enable flag + a JSON list of revealed
    # rectangles. Additive; defaults = fog off, nothing revealed.
    maps_cols_v91 = _column_names("maps")
    with engine.begin() as conn:
        if maps_cols_v91 and "fog_enabled" not in maps_cols_v91:
            conn.execute(text(
                "ALTER TABLE maps ADD COLUMN fog_enabled "
                "BOOLEAN NOT NULL DEFAULT FALSE"
            ))
        if maps_cols_v91 and "fog_revealed" not in maps_cols_v91:
            conn.execute(text(
                "ALTER TABLE maps ADD COLUMN fog_revealed JSON NOT NULL DEFAULT '[]'"
            ))

    # ---- Schema v92 (2.789.0): maps.terrain ----
    # Maps 2.0 terrain regions — a JSON list of {id,x,y,w,h,type} rectangles.
    # Additive; default empty list.
    maps_cols_v92 = _column_names("maps")
    with engine.begin() as conn:
        if maps_cols_v92 and "terrain" not in maps_cols_v92:
            conn.execute(text(
                "ALTER TABLE maps ADD COLUMN terrain JSON NOT NULL DEFAULT '[]'"
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
