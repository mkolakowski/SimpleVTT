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


VALID_THEMES = {"dark", "midnight", "dim", "light", "forest", "bubblegum", "fire"}


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
    # Per-user tab tint colors for the tabletop sidebar
    battle_tab_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    player_tab_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

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
