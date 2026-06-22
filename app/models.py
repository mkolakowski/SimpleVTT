"""SQLAlchemy ORM models for SimpleVTT."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Visibility(str, enum.Enum):
    GM_ONLY = "gm_only"
    GM_AND_ROLLER = "gm_and_roller"
    PUBLIC = "public"


class GridType(str, enum.Enum):
    SQUARE = "square"
    HEX = "hex"
    NONE = "none"


VALID_THEMES = {
    "dark", "midnight", "dim", "light", "forest", "bubblegum", "fire", "oled",
    # Fantasy themes
    "hobbiton", "hearthstone", "mosswood", "inkwell", "forge", "sepia",
}


def _default_user_theme() -> str:
    # Resolved at INSERT time (not import time) to avoid a circular
    # import — settings -> models -> database -> models — and so that an
    # operator changing ``APP_DEFAULT_THEME`` actually affects newly
    # created users (registration, Google SSO, demo seed). The server-
    # side fallback below stays a static literal because ``server_default``
    # is rendered into the CREATE TABLE statement.
    from .config import get_settings
    return get_settings().default_theme


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    google_sub: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, unique=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    theme: Mapped[str] = mapped_column(String(20), default=_default_user_theme, server_default="dark")
    # Per-user fantasy font preference (None = system default sans-serif)
    font_preference: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # Per-user tab tint colors for the tabletop sidebar
    battle_tab_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    player_tab_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Per-user display scaling. ui_scale controls overall interface zoom;
    # font_scale separately scales the root font-size. Both default to 1.0
    # and are ignored on phones (≤ 640px viewport, see base.html).
    ui_scale: Mapped[float] = mapped_column(Float, default=1.0, server_default="1.0")
    font_scale: Mapped[float] = mapped_column(Float, default=1.0, server_default="1.0")
    # Per-user multiplier applied to wheel + pinch zoom on the tabletop
    # canvas. 1.0 = default feel; lower = gentler (good for iPad pinch),
    # higher = snappier. Range clamped to [0.3, 1.5] in 0.1 steps by
    # both the slider and the server-side coerce.
    zoom_speed: Mapped[float] = mapped_column(Float, default=1.0, server_default="1.0")
    animate_gifs: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # v2.49.244: per-user roll-log drawer side. "right" (default) renders
    # roll log in the shared right sidebar with the other tabs; "left"
    # pulls roll log into its own independent left-side sidebar so a
    # player can view it alongside Battle / Characters / Settings on the
    # right. Ergonomic preference (monitor size, dominant hand) — mirrors
    # the per-user pattern for theme / font_preference / tab_color.
    roll_log_position: Mapped[str] = mapped_column(String(10), default="right", server_default="right")

    # v2.62.0 — per-user glass / frosted-card transparency. Range 1-100;
    # default 42 matches the v2.50.3 baseline alpha (every glass card
    # uses `color-mix(in srgb, var(--bg) <glass_alpha>%, transparent)`).
    # Higher = more opaque (closer to solid bg); lower = more see-
    # through. Body element renders `--glass-alpha: <value>%` so the
    # CSS reads it via `var(--glass-alpha, 42%)`.
    glass_alpha: Mapped[int] = mapped_column(Integer, default=42, server_default="42")

    # v2.67.0 — per-user reaction-prompt UX. Controls whether the
    # client surfaces a popup toast + roll-log entry when a reaction
    # event fires for a character this user owns, or only the roll-
    # log entry, or nothing at all (legacy chip-click).
    # Values: "popup" | "roll_log_only" | "off".
    reaction_prompt_mode: Mapped[str] = mapped_column(
        String(16), default="popup", server_default="popup",
    )

    # v2.84.0 — per-user toggle for the sepia theme's wood-grain
    # background pattern. v2.85.0 flipped the default from True →
    # False so the sepia theme renders the flat solid sepia color
    # out of the box; opt-in to the textured look via the /settings
    # toggle. Other themes ignore the column; it's theme-agnostic
    # so future themes can adopt the same opt-in pattern.
    sepia_texture: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false",
    )

    characters: Mapped[list["Character"]] = relationship(
        back_populates="owner", foreign_keys="Character.owner_user_id"
    )


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    gm_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    game_system: Mapped[str] = mapped_column(String(40), default="generic")
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    active_map_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("maps.id", use_alter=True, name="fk_campaign_active_map"), nullable=True
    )
    # v2.86.0: encounter-background layer. The URL of an image or video
    # rendered as a fullscreen fixed-position layer BEHIND the battle
    # map. Extends past the map's edges so the world doesn't "end" at
    # the map boundary; stays still while the map pans/zooms over it.
    # Encounters carry their own ``background_url`` and the load flow
    # copies it here — this column is the "currently displayed" handle
    # that the tabletop SSR + ``background_change`` WS broadcast read
    # from. Animated formats: GIF + animated WebP via <img>, mp4 +
    # webm via <video>. Detection lives in the template (extension).
    active_background_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    # v2.87.0: campaign-level default background. When an encounter
    # loads without its own ``background_url`` set, the load flow
    # falls back to this value so the campaign's "house" backdrop
    # stays in effect for any unbound encounter. Settable via the
    # /api/campaign/{cid}/background endpoint, which also bumps
    # ``active_background_url`` so the change is immediately visible
    # without requiring an encounter load. Null = no default; the
    # tabletop falls back to the theme's body color.
    default_background_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    # Audio: track currently playing (null = nothing); started_at is the
    # server-side timestamp of when playback began, used by clients to
    # compute the seek offset so everyone hears the same position.
    now_playing_track_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("playlist_tracks.id", use_alter=True, name="fk_campaign_now_playing_track", ondelete="SET NULL"),
        nullable=True,
    )
    now_playing_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    now_playing_loop: Mapped[bool] = mapped_column(Boolean, default=True)
    # Pause state: when non-null, audio is paused at this many seconds
    # into the track. Resume sets ``now_playing_started_at = now -
    # paused_offset`` so every client computes the same resume position
    # via the existing time-sync math, then clears this field.
    now_playing_paused_offset_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Auto-play on session start: when set, the configured playlist begins
    # playing the moment the GM clicks "Start session". ``auto_play_mode``
    # is one of "order" (start at the first track) or "shuffle" (pick a
    # random track each session). On session end the now-playing fields
    # are cleared and an audio_stop broadcast is fired.
    auto_play_playlist_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "playlists.id",
            use_alter=True,
            name="fk_campaign_auto_play_playlist",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    auto_play_mode: Mapped[str] = mapped_column(String(10), default="order")
    # Optional encounter that auto-loads when the GM clicks Start
    # session. Mirrors the auto_play_playlist_id pattern above — null
    # means "no default; do nothing extra at session start". FK uses
    # use_alter because Encounter.campaign_id already points the other
    # way and SQLAlchemy needs an explicit ALTER to break the cycle.
    default_encounter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "encounters.id",
            use_alter=True,
            name="fk_campaign_default_encounter",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    # Last-loaded encounter — the encounter currently "running" at the
    # table. Set by _perform_encounter_load; cleared (SET NULL) if the
    # encounter is deleted. Used by the Battle drawer's encounters panel
    # to pin the active encounter so the GM can see what's running even
    # when the panel is collapsed.
    current_encounter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "encounters.id",
            use_alter=True,
            name="fk_campaign_current_encounter",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    # Session lifecycle: GM must explicitly Start a session before players
    # (non-GM members) can access the tabletop. GMs and admins always have
    # access regardless. session_started_at is set the moment Start is hit.
    session_active: Mapped[bool] = mapped_column(Boolean, default=False)
    session_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # v2.5.0: house-rule toggle for potions as a bonus action. When True,
    # the action-economy tracker (planned Phase 2 from
    # docs/plans/class-content-status.md section E) will tag potion item
    # usage as a "bonus" slot consumption instead of the RAW "action".
    # Stores the preference; mechanical integration lands when Phase 2
    # of the action-economy work ships.
    potions_as_bonus_action: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")
    # v2.8.0: strict action-economy gating. When True, the over-budget
    # Layer B modal hides its Confirm button — players can't manually
    # override a spent slot from the modal. GM clicks still bypass
    # (rules-authority); GM can shift+click a chip on the init tracker
    # to manually refund a slot (Action Surge / Haste / etc.). The
    # /move endpoint additionally broadcasts a feature_used audit
    # entry on the FIRST drag that pushes a combatant past their
    # walking speed in a turn, since dragging is the GM's authoritative
    # input and can't be snapped back.
    strict_action_economy: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")
    # v2.24.0 Phase T.2: auto-apply damage to targeted creatures.
    # When False (default), /attack rolls damage + broadcasts but the
    # GM/player still manually applies HP via the init-tracker HP
    # input or the sheet HP field. When True, /attack reads the
    # target combatant's AC from sheet/template, computes hit/miss,
    # doubles damage dice on a crit, and auto-applies the resulting
    # damage to the target via _apply_hp_change (resistance from
    # Phase B halves correctly). Per the v2.21.0 plan questionnaire
    # the toggle defaults OFF so existing tables aren't surprised by
    # unexpected HP changes; GMs opt in once they trust the flow.
    auto_apply_damage: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")
    # v2.102.0: movement lock. ``movement_locked`` is the LIVE state —
    # when True, non-GM token drags are rejected by /token/move with a
    # 409 ``movement_locked`` (the player must Request movement from the
    # GM, who approves/denies). GM drags are allowed through (the GM is
    # the arbiter); the client shows the GM an advisory "move anyway?"
    # confirm. The GM flips the live state via POST /movement_lock,
    # which broadcasts ``movement_lock_update`` so every client's lock
    # chrome stays in sync. ``movement_lock_default`` is the campaign
    # setting that seeds ``movement_locked`` each time an encounter is
    # loaded — so a table that always plays with locked movement can
    # default it ON without re-toggling every encounter.
    movement_locked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")
    movement_lock_default: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")
    # GM-assigned color for the primary GM in the roll log
    gm_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Tint color for the GM Tools tab in the tabletop sidebar
    gm_tab_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # GM-forced font for all players in this campaign (None = each player's own preference)
    font_override: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # HP threshold labels for the initiative tracker player view.
    # JSON array of {"label": str, "min_pct": int} sorted descending by min_pct.
    # null = use application defaults.
    hp_thresholds: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    gm: Mapped[User] = relationship(foreign_keys=[gm_user_id])
    maps: Mapped[list["Map"]] = relationship(
        back_populates="campaign", foreign_keys="Map.campaign_id", cascade="all, delete-orphan"
    )
    active_map: Mapped[Optional["Map"]] = relationship(
        foreign_keys=[active_map_id], post_update=True
    )
    characters: Mapped[list["Character"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    rolls: Mapped[list["DiceRoll"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class Map(Base):
    __tablename__ = "maps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    grid_type: Mapped[GridType] = mapped_column(Enum(GridType), default=GridType.SQUARE)
    grid_size_px: Mapped[int] = mapped_column(Integer, default=70)
    grid_offset_x: Mapped[int] = mapped_column(Integer, default=0)
    grid_offset_y: Mapped[int] = mapped_column(Integer, default=0)
    # v2.4.0: per-map "show grid overlay" toggle. ``grid_type`` keeps
    # driving token snapping (square / hex / none) so the GM can switch
    # the overlay off on a map that already has a grid baked into its
    # background image without losing snap-to-grid token placement.
    # ``grid_type == NONE`` already disabled both overlay AND snapping;
    # this flag adds the orthogonal "snap yes, overlay no" combination.
    show_grid: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    width_px: Mapped[int] = mapped_column(Integer, default=2000)
    height_px: Mapped[int] = mapped_column(Integer, default=1500)
    # Per-character session-prep spawn points. JSON dict keyed by
    # character id (as a string, since JSON dict keys must be strings)
    # to ``{x, y}``. The GM sets these ahead of a session so they can
    # later drop player tokens onto the map at designated spots in one
    # click — including split-party setups where each PC starts in a
    # different room / corner / level. See ``/maps/{mid}/spawn``
    # endpoints for the per-character set/clear flow and
    # ``/maps/{mid}/place-players-at-spawn`` for the bulk-place trigger.
    # Visibility is GM-only; player clients don't render the markers.
    # NOTE (v0.73.0): the feature moved onto the Encounter model; the
    # column stays for backward-compat but isn't read by the app.
    player_spawns: Mapped[dict] = mapped_column(JSON, default=dict)
    # Free-form GM-side tags for library organisation. Same shape as
    # Encounter.tags and Playlist.tags.
    tags: Mapped[list] = mapped_column(JSON, default=list)
    folder: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, default="", server_default="")
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaign: Mapped[Campaign] = relationship(back_populates="maps", foreign_keys=[campaign_id])
    tokens: Mapped[list["Token"]] = relationship(
        back_populates="map", cascade="all, delete-orphan"
    )


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120))
    template: Mapped[str] = mapped_column(String(40), default="generic")
    sheet: Mapped[dict] = mapped_column(JSON, default=dict)
    portrait_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ring_style: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaign: Mapped[Optional[Campaign]] = relationship(back_populates="characters")
    owner: Mapped[Optional[User]] = relationship(
        back_populates="characters", foreign_keys=[owner_user_id]
    )
    tokens: Mapped[list["Token"]] = relationship(back_populates="character")


class Token(Base):
    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    map_id: Mapped[int] = mapped_column(ForeignKey("maps.id", ondelete="CASCADE"))
    character_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    controller_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    label: Mapped[str] = mapped_column(String(120), default="")
    color: Mapped[str] = mapped_column(String(20), default="#cc3333")
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    x: Mapped[float] = mapped_column(Float, default=0)
    y: Mapped[float] = mapped_column(Float, default=0)
    size: Mapped[int] = mapped_column(Integer, default=1)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    # v2.64.0 — F2 fog-of-war: per-user-id hidden list. When a user's
    # id appears in this list, GET /tokens (non-GM) omits the token
    # AND the canvas render filter skips it on broadcasts. GMs always
    # see every token regardless. Distinct from `is_hidden` (legacy
    # "hidden from everyone but GM" boolean) — the new field is
    # additive: specific user_ids can be hidden from while others
    # can still see.
    hidden_from_user_ids: Mapped[list] = mapped_column(
        JSON, default=list, server_default="[]",
    )
    token_template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("token_templates.id", use_alter=True, name="fk_token_template", ondelete="SET NULL"),
        nullable=True,
    )
    # v2.99.52 — plan-movement-oa-flow Phase 1: faction tag used by
    # `_check_opportunity_attack_triggers` to skip same-team OAs.
    # RAW: OA only fires on a hostile creature. Values:
    #   "hero" / "villain" — explicit factions; OA fires across,
    #     skips within.
    #   "neutral" (default) — back-compat for pre-Phase-1 campaigns;
    #     OA fires regardless of the OTHER side's team. Tokens
    #     opt into the same-team filter by getting a non-neutral
    #     tag from the GM via the Token Management UI (Phase 2).
    team: Mapped[str] = mapped_column(
        String(16), default="neutral", server_default="neutral",
    )
    # v2.99.168 — token-disguise primitive. When a Druid Wild-Shapes
    # or a Sorcerer Polymorphs, the original token's label / size /
    # (future) image_url are snapshotted into `disguise.original`
    # and replaced with the new form's values. /revert restores
    # the originals and clears the disguise. Storage is per-token
    # (not per-sheet) so a Polymorph targeting an enemy NPC can
    # stash the disguise on the enemy's token without needing the
    # enemy to have a Character row. JSON shape:
    #   { "source": "wild-shape" | "polymorph",
    #     "original": {"label": "...", "size": N},
    #     "form_name": "Wolf",
    #     "applied_at": ISO8601 string }
    # None / null when the token is in its native form.
    disguise: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=None,
    )

    map: Mapped[Map] = relationship(back_populates="tokens")
    character: Mapped[Optional[Character]] = relationship(back_populates="tokens")
    controller: Mapped[Optional[User]] = relationship(foreign_keys=[controller_user_id])


class DiceRoll(Base):
    __tablename__ = "dice_rolls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expression: Mapped[str] = mapped_column(String(120))
    breakdown: Mapped[str] = mapped_column(Text, default="")
    total: Mapped[int] = mapped_column(Integer, default=0)
    visibility: Mapped[Visibility] = mapped_column(
        Enum(Visibility), default=Visibility.PUBLIC
    )
    note: Mapped[str] = mapped_column(String(200), default="")
    # v2.115.0 — character this roll is attributed to (the rolling PC),
    # when known. Persisted so the server-rendered roll history can
    # surface the reroll button (Lucky etc.) for past rolls, not just
    # the live WS-delivered ones. Nullable: char-less rolls (raw dice,
    # monster rolls) leave it None. SET NULL if the character is deleted.
    character_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaign: Mapped[Campaign] = relationship(back_populates="rolls")
    user: Mapped[User] = relationship()


class CampaignMembership(Base):
    """Users invited to a campaign (other than the primary GM/owner).

    is_gm=True marks a co-GM with full GM powers in this campaign.
    color is a GM-assigned hex color used to highlight this member in the roll log.
    """
    __tablename__ = "campaign_memberships"
    __table_args__ = (UniqueConstraint("campaign_id", "user_id", name="uq_membership"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    is_gm: Mapped[bool] = mapped_column(Boolean, default=False)
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


AUDIO_CATEGORIES = ("music", "sfx", "environment")
AUDIO_CATEGORY_LABELS = {"music": "Music", "sfx": "Sound Effects", "environment": "Environment"}


class Playlist(Base):
    """A named collection of audio tracks the GM can broadcast to players."""
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    # Short blurb (e.g. "Boss-fight crescendo", "Tavern ambience"). Shown
    # next to the name in the tabletop GM Music panel; the campaign
    # settings page exposes a small input for editing.
    description: Mapped[str] = mapped_column(String(200), default="")
    # Free-form GM-side tags for library organisation. Same shape as
    # Encounter.tags: a JSON list of short strings.
    tags: Mapped[list] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(20), default="music")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tracks: Mapped[list["PlaylistTrack"]] = relationship(
        back_populates="playlist",
        cascade="all, delete-orphan",
        order_by="PlaylistTrack.position",
    )


class PlaylistTrack(Base):
    """One audio file inside a playlist, served from /static/uploads/audio/."""
    __tablename__ = "playlist_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    file_url: Mapped[str] = mapped_column(String(500))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    track_artist: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    track_album: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    track_genre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    track_year: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)

    playlist: Mapped[Playlist] = relationship(back_populates="tracks")


class UserAudioPreference(Base):
    """Per-user-per-track volume override (legacy — superseded by UserAudioCategoryPref)."""
    __tablename__ = "user_audio_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "track_id", name="uq_user_track_pref"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    track_id: Mapped[int] = mapped_column(ForeignKey("playlist_tracks.id", ondelete="CASCADE"))
    volume: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class UserAudioCategoryPref(Base):
    """Per-user-per-category volume (0.0-1.0). Categories: music, sfx, environment.
    Stored server-side so preferences follow the user across browsers/devices.
    Effective playback volume = master × category_volume."""
    __tablename__ = "user_audio_category_prefs"
    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_user_category_pref"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(20))
    volume: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AudioPlayEvent(Base):
    """One row per audio play. Recorded by the audio helpers in
    audio_routes.py so the campaign settings page can show what's been
    played, when, how long, and how it ended.

    Lifecycle: a row is inserted with ``ended_at = NULL`` when a track
    starts playing; the row is finalized (ended_at set + ended_reason
    set + duration computed) when the next track starts OR audio stops
    OR the session ends. A dangling NULL row means the play was
    interrupted by a server restart — the UI shows it as "in flight".

    ``track_name`` and ``playlist_name`` snapshot the names at play time
    so the log survives a track / playlist rename or deletion.

    ``ended_reason`` values:
      - ``completed``      — natural end of file (client called /audio/next)
      - ``skipped``        — GM started a different track
      - ``stopped``        — GM clicked Stop or hit /audio/stop
      - ``session_end``    — session ended while audio was playing
      - ``ongoing``        — still playing (ended_at is null)
    ``source`` values:
      - ``manual``         — GM clicked play in the GM Tools music panel
      - ``auto_start``     — fired by session-start auto-play (v0.58.0)
      - ``auto_next``      — fired by /audio/next when a track ended
      - ``loop``           — same track replayed because loop is on
    """
    __tablename__ = "audio_play_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    # Both FKs are nullable + ON DELETE SET NULL so deleting a track or
    # playlist doesn't strand history rows; the snapshot name fields
    # below still let the GM see "Tavern Theme (deleted)" in the log.
    track_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("playlist_tracks.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    playlist_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("playlists.id", ondelete="SET NULL"),
        nullable=True,
    )
    track_name: Mapped[str] = mapped_column(String(300), default="")
    playlist_name: Mapped[str] = mapped_column(String(200), default="")
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True,
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Seconds the track played. Computed when the row is finalized.
    duration_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ended_reason: Mapped[str] = mapped_column(String(20), default="ongoing")
    source: Mapped[str] = mapped_column(String(20), default="manual")
    triggered_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )


class TokenTemplate(Base):
    """Reusable token with a character sheet for NPCs/monsters."""
    __tablename__ = "token_templates"
    __table_args__ = ()

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    template: Mapped[str] = mapped_column(String(40), default="generic")
    sheet: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RollRequest(Base):
    """A GM-posted roll prompt that any player (or the GM acting as a token)
    can respond to by clicking a button.  The resulting DiceRoll is a normal
    roll record; the request itself is ephemeral (shown live; not replayed on
    refresh, but kept in the DB for audit purposes).

    stat_key controls which sheet stat is resolved server-side before rolling:
      • Saving throw  → "str_save" / "dex_save" / … / "cha_save"
      • Ability check → "str_check" / … / "cha_check"
      • Skill check   → exact skill name from DND5E_TEMPLATE, e.g. "Perception"
      • Empty/None    → roll base_expression with no sheet modifier
    """
    __tablename__ = "roll_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Human-readable label shown in the roll-request card, e.g. "CON Save DC 15"
    label: Mapped[str] = mapped_column(String(200))
    # Dice expression before the sheet modifier is appended, e.g. "1d20"
    base_expression: Mapped[str] = mapped_column(String(60), default="1d20")
    # Stat key for D&D 5e sheet resolution (see docstring above)
    stat_key: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    # Optional difficulty class for pass/fail display
    dc: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Visibility applied to every responding DiceRoll
    visibility: Mapped[Visibility] = mapped_column(
        Enum(Visibility), default=Visibility.PUBLIC
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    creator: Mapped["User"] = relationship(foreign_keys=[created_by_user_id])


# ---- Removed in v2.0.0 ----
# CustomClass / CustomBackground / CustomFeat / CustomMonster / CustomRace /
# CustomSubclass were dropped at v2.0.0. The corresponding tables are exported
# to per-slug JSON files under the homebrew Docker volume by
# app/_migrate_v52.py (schema v52), then DROP TABLEd in the same boot
# migration. Going forward all homebrew lives in
# app/data/homebrew/<system>/<scope>/<type>/<slug>.json and is read
# through app/local_content.py.


class Encounter(Base):
    """A GM-saved bundle of {map, tokens, initiative seed, optional playlist}
    that can be reloaded at the table in a single click.

    Phase 1 (v0.64.0) ships the table + a read-only listing UI; save /
    load / edit / delete flows arrive in later phases. See
    ``docs/encounters-plan.md`` for the full design.

    The ``payload`` JSON column carries the per-encounter token list +
    initiative snapshot:

      {
        "tokens": [
          {"template_id": int|null, "character_id": int|null,
           "label_override": str, "color_override": str|null,
           "size": int, "x": float, "y": float, "is_hidden": bool},
          ...
        ],
        "initiative": [
          {"name": str, "init": int, "hp_max": int, "hp_current": int,
           "color": str|null, "token_idx": int|null},
          ...
        ],
      }

    ``map_id`` and ``auto_play_playlist_id`` are nullable + ON DELETE
    SET NULL so a deleted map or playlist degrades the load flow
    gracefully (skip the map switch / skip the audio start) instead of
    cascading the encounter out of existence.
    """
    __tablename__ = "encounters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    map_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("maps.id", ondelete="SET NULL"), nullable=True
    )
    # v2.86.0: per-encounter background URL — image or video — that's
    # copied to ``campaign.active_background_url`` when the encounter
    # loads. See Campaign.active_background_url for the rendering
    # contract. Null = the encounter doesn't override the current
    # background (load leaves whatever's displayed alone).
    background_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    auto_play_playlist_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("playlists.id", ondelete="SET NULL"), nullable=True
    )
    auto_play_mode: Mapped[str] = mapped_column(String(10), default="order")
    auto_play_track_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("playlist_tracks.id", ondelete="SET NULL"), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    # Free-form tags for GM-side grouping in the library UI (e.g. "boss",
    # "random", "set-piece"). Stored as a JSON list of short strings;
    # rendering and filtering happen client-side.
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # Per-encounter player spawn points. When ``use_spawn_points`` is
    # true the load flow places each player at the matching coord in
    # ``spawn_points`` (dict keyed by character id as a string) instead
    # of falling back to the snapshot's saved positions. Lets the GM
    # designate player starting spots ahead of time during prep without
    # having to first stage tokens on the live tabletop.
    use_spawn_points: Mapped[bool] = mapped_column(Boolean, default=False)
    spawn_points: Mapped[dict] = mapped_column(JSON, default=dict)
    # Optional single-level folder name for library grouping. Empty
    # string = "Unfiled" group in the UI. Free-form text — no
    # registration of folder names, they're just whatever strings the
    # GM has typed across the campaign's encounters.
    folder: Mapped[str] = mapped_column(String(120), default="")
    # Audio behaviour on load when no playlist is bound to the
    # encounter. False (default) = leave the currently-playing audio
    # alone (preserves the pre-v0.78 behaviour). True = stop audio on
    # load. When ``auto_play_playlist_id`` IS set, this flag is ignored
    # and the playlist takes over playback regardless.
    stop_audio_on_load: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    campaign: Mapped[Campaign] = relationship(foreign_keys=[campaign_id])
    map: Mapped[Optional[Map]] = relationship(foreign_keys=[map_id])
    auto_play_playlist: Mapped[Optional[Playlist]] = relationship(
        foreign_keys=[auto_play_playlist_id]
    )


class ConcentrationEffect(Base):
    """One active concentration spell per character (at most one at a time).

    rounds_remaining = None means unlimited (tracked by scene, not rounds).
    Rounds decrement at the END of the concentrating character's initiative turn.
    """
    __tablename__ = "concentration_effects"
    __table_args__ = (
        UniqueConstraint("campaign_id", "character_id", name="uq_conc_char"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    spell_name: Mapped[str] = mapped_column(String(120))
    rounds_remaining: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AdminAuditLog(Base):
    """Generic admin-action audit log (v2.427.0, schema v71).

    Per ``docs/plans/cloudflare-edge-banning.md``. Records every
    admin-triggered action that has a security or coordination
    consequence — Phase 1 logs cloudflare-ban / cloudflare-unban;
    future phases (campaign-delete, user-purge, demo-magic-link
    mint) drop into the same schema.

    The table is intentionally generic — ``action`` is a free-form
    ``subsystem.event`` slug, ``target`` is the principal subject
    of the action (an IP, a user id, a rule id), and ``notes`` is
    operator commentary. Queries against the table go by
    ``actor_user_id`` (who's been clicking what) or ``target``
    (when did anyone touch this IP).
    """
    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    target: Mapped[str] = mapped_column(String(200), nullable=False)
    scope: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cloudflare_rule_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class DemoMagicLink(Base):
    """Single-use enforcement for demo magic-link tokens (v2.425.0,
    schema v70). See ``docs/plans/demo-magic-link.md``.

    Every successful verify writes the token's jti (16 random bytes
    base64url-encoded — 22 chars) so a second attempt with the same
    token fails the unique-constraint and 401s as a replay.

    The table is intentionally tiny — a GC sweep (out of scope for
    Phase 1; filed for Phase 2) deletes rows older than 2× the TTL
    so it stays small even on a busy public demo. SimpleVTT itself
    never reads these rows except via the atomic INSERT-or-violate
    path in ``demo_magic_link_routes._consume_jti``.
    """
    __tablename__ = "demo_magic_links"

    jti: Mapped[str] = mapped_column(String(40), primary_key=True)
    sub: Mapped[str] = mapped_column(String(200), nullable=False)
    consumed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class Battle(Base):
    """Persistent per-campaign battle / initiative-tracker state.

    Exactly one row per campaign (the active battle), keyed on
    ``campaign_id`` as the primary key so a write is a natural upsert.
    The ``state`` JSON blob mirrors the in-memory ``CampaignHub._battle``
    cache verbatim (``{"combatants": [...], "turn_index": N, "round": N,
    "active": bool, ...}``).

    Why this exists (v2.101.0): before this table the hub was RAM-only,
    so an app restart or the hourly demo reseed silently emptied it and
    every server-side battle read — opportunity-attack detection, the
    over-speed movement gate, reaction-prompt routing — found zero
    combatants and no-oped until the GM next mutated the battle. The
    v2.100.6 GM-load localStorage→hub push was a client-side band-aid for
    the same bug. With this row the hub becomes a write-through cache:
    ``set_battle`` persists here, and ``get_battle`` lazily rehydrates
    from here on a cache miss (i.e. after a restart), so the server's
    authoritative battle state survives a process bounce. See
    ``realtime.CampaignHub`` for the write-through/lazy-load contract.
    """
    __tablename__ = "battles"

    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True,
    )
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


# Notes & Handouts (docs/plans/notes-and-handouts.md).
NOTE_KINDS = ("gm_note", "player_note")
NOTE_VISIBILITIES = ("gm_only", "public", "private")


class CampaignNote(Base):
    """A GM prep note or a player's personal note (v2.554.0, schema v72).

    See ``docs/plans/notes-and-handouts.md``. Phase 1 ships the
    ``gm_note`` kind (GM/co-GM prep, always ``gm_only`` visibility);
    later phases extend the same table:

      - ``kind == "gm_note"``     → ``visibility == "gm_only"`` (GM/co-GM).
      - ``kind == "player_note"`` → ``visibility`` ``"public"`` (all
        campaign members) or ``"private"`` (Phase 4: end-to-end encrypted,
        author-only).

    For a non-private note the plaintext lives in ``title`` / ``body``
    (markdown). For a private note (Phase 4) those are NULL and the
    AES-GCM ciphertext envelopes live in ``enc_title`` / ``enc_body`` with
    ``is_encrypted == True`` — the server stores opaque blobs it has no
    key to read. ``kind`` / ``visibility`` are plain strings validated at
    the route layer (NOTE_KINDS / NOTE_VISIBILITIES) rather than DB enums
    so later phases can add values without a postgres enum-type migration.
    """
    __tablename__ = "campaign_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True,
    )
    author_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True,
    )
    kind: Mapped[str] = mapped_column(String(20), default="gm_note")
    visibility: Mapped[str] = mapped_column(String(20), default="gm_only")
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    # Phase 4 ciphertext envelopes for private notes; NULL otherwise.
    enc_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enc_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_encrypted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false",
    )
    folder: Mapped[str] = mapped_column(
        String(120), default="", server_default="",
    )
    pinned: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class Handout(Base):
    """A GM-authored handout that can be revealed to the table (v2.555.0,
    schema v73). See ``docs/plans/notes-and-handouts.md`` Phase 2.

    Handouts are GM-authored content meant to be shown — a letter, a map
    fragment, an item card, an NPC portrait. Unlike notes they are never
    encrypted; the "who can see it" control is ``revealed`` + ``reveal_to``:

      - ``revealed == False``     → GM/co-GM only (still being prepped).
      - ``revealed == True`` and  → every campaign member sees it.
        ``reveal_to == "all"``
      - ``revealed == True`` and  → only the listed user_ids (plus the
        ``reveal_to == [uid…]``     GM) see it.

    Revealing broadcasts a ``handout_revealed`` WS event scoped to the
    targets via ``hub.broadcast(..., recipient_filter=...)`` — a handout
    revealed to one player never toasts on another player's screen.
    ``reveal_to`` is JSON holding either the string ``"all"`` or a list
    of user_ids (same JSON column type as ``Token.hidden_from_user_ids``).
    """
    __tablename__ = "handouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True,
    )
    author_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    folder: Mapped[str] = mapped_column(
        String(120), default="", server_default="",
    )
    revealed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false",
    )
    # "all" (string) OR a list of user_ids. Default empty list = revealed
    # to nobody (only meaningful once `revealed` is True). Typed Mapped[Any]
    # because the JSON value is a str OR a list — the column type is given
    # explicitly (JSON), so the annotation is just the ORM mapped marker.
    reveal_to: Mapped[Any] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )
