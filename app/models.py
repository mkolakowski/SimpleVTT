"""SQLAlchemy ORM models for SimpleVTT."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

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
    "hobbiton", "hearthstone", "mosswood", "inkwell", "forge",
}


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
    theme: Mapped[str] = mapped_column(String(20), default="dark", server_default="dark")
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
    animate_gifs: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

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
    # Audio: track currently playing (null = nothing); started_at is the
    # server-side timestamp of when playback began, used by clients to
    # compute the seek offset so everyone hears the same position.
    now_playing_track_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("playlist_tracks.id", use_alter=True, name="fk_campaign_now_playing_track", ondelete="SET NULL"),
        nullable=True,
    )
    now_playing_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    now_playing_loop: Mapped[bool] = mapped_column(Boolean, default=True)
    # Session lifecycle: GM must explicitly Start a session before players
    # (non-GM members) can access the tabletop. GMs and admins always have
    # access regardless. session_started_at is set the moment Start is hit.
    session_active: Mapped[bool] = mapped_column(Boolean, default=False)
    session_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # GM-assigned color for the primary GM in the roll log
    gm_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Tint color for the GM Tools tab in the tabletop sidebar
    gm_tab_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # GM-forced font for all players in this campaign (None = each player's own preference)
    font_override: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
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
    width_px: Mapped[int] = mapped_column(Integer, default=2000)
    height_px: Mapped[int] = mapped_column(Integer, default=1500)
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
    token_template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("token_templates.id", use_alter=True, name="fk_token_template", ondelete="SET NULL"),
        nullable=True,
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


class CustomClass(Base):
    """A homebrew base class authored within a campaign.

    Picked up by the local-features resolver under scope ``campaign:<id>``
    and returned in the same shape Open5e responses use after parsing:
    ``{name, hit_die, prof_*, spellcasting_ability, equipment, features}``.

    The features field is a structured list ``[{name, level, desc}, ...]``
    (same shape custom subclasses use); the class-detail endpoint flattens
    it into a markdown blob for legacy frontend consumers when serving.

    First-pass MVP: no class spell list, no per-rest resource tables, no
    multiclass-prereq metadata.  Those are bigger surfaces and will arrive
    in later iterations if and when they're needed.
    """
    __tablename__ = "custom_classes"
    __table_args__ = (
        UniqueConstraint("campaign_id", "class_slug", name="uq_custom_class"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    class_slug: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(120))
    hit_die: Mapped[int] = mapped_column(Integer, default=8)
    prof_armor: Mapped[str] = mapped_column(String(500), default="")
    prof_weapons: Mapped[str] = mapped_column(String(500), default="")
    prof_tools: Mapped[str] = mapped_column(String(500), default="")
    prof_saving_throws: Mapped[str] = mapped_column(String(120), default="")
    prof_skills: Mapped[str] = mapped_column(String(500), default="")
    spellcasting_ability: Mapped[str] = mapped_column(String(10), default="")
    equipment: Mapped[str] = mapped_column(Text, default="")
    features: Mapped[list] = mapped_column(JSON, default=list)
    # Spell list: a flat list of Open5e spell slugs available to characters
    # of this homebrew class.  Populated by the GM via the spell picker on
    # the campaign settings page; surfaced to the player's spell picker when
    # they filter by ``spell_list=<this class's slug>``.
    spell_list: Mapped[list] = mapped_column(JSON, default=list)
    # Multiclass prerequisites: {ability: min_score, …}, e.g. {"str": 13}.
    # ``multiclass_prereq_mode`` is "all" (every ability listed must meet
    # its minimum) or "any" (at least one is enough — matches Fighter's
    # STR-or-DEX rule).  ``multiclass_proficiencies`` is a free-text
    # description of what the character gains on multiclassing into this
    # class (e.g. "Light armor, medium armor, shields, simple weapons").
    multiclass_prereq_abilities: Mapped[dict] = mapped_column(JSON, default=dict)
    multiclass_prereq_mode: Mapped[str] = mapped_column(String(8), default="all")
    multiclass_proficiencies: Mapped[str] = mapped_column(String(500), default="")
    # Per-rest resource counters (Rage, Channel Divinity, Ki, Action Surge,
    # Bardic Inspiration, …).  Stored as JSON-serialisable records — the
    # frontend's static resources table accepts JS functions for "max", so
    # the sheet merge translates these declarative kinds into runtime
    # closures at load time.  See ``_parse_class_resources_json`` for the
    # exact shape this column accepts.
    resources: Mapped[list] = mapped_column(JSON, default=list)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    campaign: Mapped[Campaign] = relationship(foreign_keys=[campaign_id])
    created_by: Mapped[Optional[User]] = relationship(foreign_keys=[created_by_user_id])


class CustomBackground(Base):
    """A homebrew character background authored within a campaign.

    Mirrors the Open5e v1 background shape: name, description, four
    proficiency strings (skills / tools / languages / equipment), and a
    single signature feature (Feature name + description). Open5e's
    longer ``suggested_characteristics`` text (personality traits,
    bonds, ideals, flaws) is intentionally omitted from MVP — it's
    roleplaying flavor with no mechanical effect.
    """
    __tablename__ = "custom_backgrounds"
    __table_args__ = (
        UniqueConstraint("campaign_id", "background_slug", name="uq_custom_background"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    background_slug: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    skill_proficiencies: Mapped[str] = mapped_column(String(500), default="")
    tool_proficiencies: Mapped[str] = mapped_column(String(500), default="")
    languages: Mapped[str] = mapped_column(String(500), default="")
    equipment: Mapped[str] = mapped_column(Text, default="")
    feature_name: Mapped[str] = mapped_column(String(160), default="")
    feature_desc: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    campaign: Mapped[Campaign] = relationship(foreign_keys=[campaign_id])
    created_by: Mapped[Optional[User]] = relationship(foreign_keys=[created_by_user_id])


class CustomFeat(Base):
    """A homebrew feat authored within a campaign.

    Smallest of the content types — name, prerequisite text, and the
    full description. Mechanical effects are described in the body
    rather than encoded as structured rules (matches how Open5e ships
    them today).
    """
    __tablename__ = "custom_feats"
    __table_args__ = (
        UniqueConstraint("campaign_id", "feat_slug", name="uq_custom_feat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    feat_slug: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    prerequisite: Mapped[str] = mapped_column(String(500), default="")
    desc: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    campaign: Mapped[Campaign] = relationship(foreign_keys=[campaign_id])
    created_by: Mapped[Optional[User]] = relationship(foreign_keys=[created_by_user_id])


class CustomMonster(Base):
    """A homebrew monster / NPC stat block authored within a campaign.

    Used by the Wild Shape / Polymorph beast picker (which filters by
    type=beast) and by the token-template flow (any type).  Picked up by
    the local-features resolver under scope ``campaign:<id>`` and returned
    in the same lite shape Open5e v2 yields after normalisation so the
    existing picker doesn't need to know the difference.

    MVP scope: identity + combat stats + six abilities + senses/languages
    as text + CR text + four parallel action lists. Defers: structured
    saves/skills with proficient flags, spell lists, lair / regional /
    legendary lair actions, multi-form stats.
    """
    __tablename__ = "custom_monsters"
    __table_args__ = (
        UniqueConstraint("campaign_id", "monster_slug", name="uq_custom_monster"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    monster_slug: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    size: Mapped[str] = mapped_column(String(40), default="Medium")
    type: Mapped[str] = mapped_column(String(60), default="beast")
    alignment: Mapped[str] = mapped_column(String(120), default="unaligned")
    # Combat
    armor_class: Mapped[int] = mapped_column(Integer, default=10)
    armor_desc: Mapped[str] = mapped_column(String(120), default="")
    hit_points: Mapped[int] = mapped_column(Integer, default=1)
    hit_dice: Mapped[str] = mapped_column(String(40), default="")
    speed: Mapped[dict] = mapped_column(JSON, default=dict)
    # Abilities (six int scores)
    strength: Mapped[int] = mapped_column(Integer, default=10)
    dexterity: Mapped[int] = mapped_column(Integer, default=10)
    constitution: Mapped[int] = mapped_column(Integer, default=10)
    intelligence: Mapped[int] = mapped_column(Integer, default=10)
    wisdom: Mapped[int] = mapped_column(Integer, default=10)
    charisma: Mapped[int] = mapped_column(Integer, default=10)
    # Defenses (free text — structured save/skill bonuses deferred to v2)
    damage_vulnerabilities: Mapped[str] = mapped_column(Text, default="")
    damage_resistances: Mapped[str] = mapped_column(Text, default="")
    damage_immunities: Mapped[str] = mapped_column(Text, default="")
    condition_immunities: Mapped[str] = mapped_column(Text, default="")
    # Senses / langs / CR (all text — CR supports "1/4" etc.)
    senses: Mapped[str] = mapped_column(Text, default="")
    languages: Mapped[str] = mapped_column(Text, default="")
    challenge_rating: Mapped[str] = mapped_column(String(20), default="0")
    # Action lists, each a ``[{name, desc, level}]`` shape. Level is
    # ignored for monsters but kept so the existing features-editor and
    # parser work without modification.
    actions: Mapped[list] = mapped_column(JSON, default=list)
    reactions: Mapped[list] = mapped_column(JSON, default=list)
    special_abilities: Mapped[list] = mapped_column(JSON, default=list)
    legendary_actions: Mapped[list] = mapped_column(JSON, default=list)

    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    campaign: Mapped[Campaign] = relationship(foreign_keys=[campaign_id])
    created_by: Mapped[Optional[User]] = relationship(foreign_keys=[created_by_user_id])


class CustomRace(Base):
    """A homebrew race authored within a campaign.

    Picked up by the local-features resolver under scope ``campaign:<id>``
    and returned in the same shape Open5e responses use after parsing:
    ``{text, name, flavor, traits: [{name, level, desc}, ...]}``. The
    ``flavor`` block is synthesised server-side from the structured
    stat fields (ability bonuses, size, speed, age, alignment, languages)
    on read, so the GM doesn't have to format the summary string by hand.
    """
    __tablename__ = "custom_races"
    __table_args__ = (
        UniqueConstraint("campaign_id", "race_slug", name="uq_custom_race"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    race_slug: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(120))
    # Open5e shape: list of ``{attribute, bonus}`` so the existing parser /
    # formatter helpers in open5e_local can render without translation.
    ability_bonuses: Mapped[list] = mapped_column(JSON, default=list)
    size: Mapped[str] = mapped_column(String(40), default="")
    speed: Mapped[int] = mapped_column(Integer, default=30)
    age: Mapped[str] = mapped_column(Text, default="")
    alignment: Mapped[str] = mapped_column(Text, default="")
    languages: Mapped[str] = mapped_column(Text, default="")
    # Structured traits, same shape as feature lists.  Level is usually
    # null for races but the field is kept so the existing renderer's
    # level-gating fall-through (lvl == null = always visible) works.
    traits: Mapped[list] = mapped_column(JSON, default=list)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    campaign: Mapped[Campaign] = relationship(foreign_keys=[campaign_id])
    created_by: Mapped[Optional[User]] = relationship(foreign_keys=[created_by_user_id])


class CustomSubclass(Base):
    """A homebrew subclass authored within a campaign.

    Picked up by the local-features resolver under scope ``campaign:<id>``
    and returned in the same shape Open5e responses use after parsing:
    ``{name, flavor, features: [{name, level, desc}, ...]}``.  ``sub_slug``
    is unique per ``(campaign_id, class_slug)`` so the same parent class
    can host multiple homebrew subclasses and a class can't host two
    homebrew subclasses with colliding slugs.

    No authoring UI yet — phase 1 is backend wiring only.  Rows can be
    inserted by direct SQL for testing; phase 2 adds a GM-only form on
    the campaign settings page.
    """
    __tablename__ = "custom_subclasses"
    __table_args__ = (
        UniqueConstraint("campaign_id", "class_slug", "sub_slug", name="uq_custom_subclass"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    class_slug: Mapped[str] = mapped_column(String(60))
    sub_slug: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    flavor: Mapped[str] = mapped_column(Text, default="")
    features: Mapped[list] = mapped_column(JSON, default=list)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    campaign: Mapped[Campaign] = relationship(foreign_keys=[campaign_id])
    created_by: Mapped[Optional[User]] = relationship(foreign_keys=[created_by_user_id])


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
