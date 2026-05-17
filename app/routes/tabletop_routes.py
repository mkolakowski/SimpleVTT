"""Tabletop pages + REST/WebSocket APIs.

REST is used for state-changing actions (move token, roll dice, edit sheet).
The WebSocket pushes those changes to other connected clients.
"""
from __future__ import annotations

import logging
import os
import re as _re
import time as _time
import uuid
from datetime import timezone
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import dice as dice_mod
from ..auth import get_current_user, require_user
from ..config import get_settings
from ..database import SessionLocal, get_db
from ..game_systems import SYSTEMS, get_system, system_choices
from ..models import (
    AudioPlayEvent,
    Campaign,
    CampaignMembership,
    Character,
    ConcentrationEffect,
    DiceRoll,
    Encounter,
    GridType,
    Map,
    Playlist,
    PlaylistTrack,
    RollRequest,
    Token,
    TokenTemplate,
    User,
    Visibility,
)
from ..realtime import hub
from .. import local_content
from ..sheet_templates import (
    class_levels_summary,
    class_slug as _class_slug,
    get_template,
    normalize_dnd5e_sheet,
)
from ..templates import templates


router = APIRouter()
log = logging.getLogger(__name__)

_OPEN5E_BASE = os.getenv("OPEN5E_BASE_URL", "https://api.open5e.com").rstrip("/")

# In-memory heal-claim store (cast_id → claim dict). Entries expire after 8 h.
_heal_claims: dict[str, dict] = {}

def _purge_heal_claims() -> None:
    now = _time.time()
    for k in [k for k, v in _heal_claims.items() if v["expires"] < now]:
        del _heal_claims[k]


# v2.5.5 (action-economy Phase 2b): server-side mirrors of the JS
# helpers in tabletop.html. Full-character-sheet clicks (.atk-strike,
# .sp-cast) live on a separate page from the tabletop, so the player's
# browser can't directly mutate the GM's init-tracker chips. Instead
# cast_spell / use_attack call _mark_battle_economy which updates the
# in-memory hub state and broadcasts ``economy_update``; both GM and
# player tabletop clients listen and re-render. Mini-sheet / monster
# clicks (Phase 2) still go through the JS path because they happen
# inside the tabletop page where ``battle`` is already in scope.

def _casting_time_to_economy(ct: str) -> str:
    """Map a spell's ``casting_time`` string to an economy slot.

    Mirrors ``_castingTimeToEconomy`` in tabletop.html. Returns one of
    ``action`` / ``bonus`` / ``reaction`` / ``none``; the ``none`` branch
    covers cantrip-free utility spells (10-minute rituals, etc.) and
    legacy rows with missing casting_time.
    """
    lc = (ct or "").lower()
    if "bonus action" in lc:
        return "bonus"
    if "reaction" in lc:
        return "reaction"
    if "action" in lc:
        return "action"
    return "none"


# v2.6.0 (action-economy Phase 3): Python mirror of
# app/static/dnd5e_feature_economy.js. The /use_feature endpoint reads
# this dict to derive the slot from a (feature_key, option_key) pair
# instead of trusting the client. Keep the two tables in sync — slot
# values diverge → server discards the client's claim and uses the
# canonical one, so silent UI-only changes won't grant phantom slots.
# Only the slot field needs mirroring (labels / descs are display-only
# and live entirely client-side; the roll-log entry posts the
# server-side display strings via the request body but the slot is
# always re-derived here).
_FEATURE_ECONOMY: dict[str, dict] = {
    "cunning-action": {
        "slot": "bonus",
        "options": {"dash": {}, "disengage": {}, "hide": {}},
    },
    "second-wind": {"slot": "bonus"},
    "action-surge": {"slot": "free"},
    "channel-divinity": {
        "slot": "action",
        "options": {
            "turn-undead": {},
            "preserve-life": {},
            "radiance-of-the-dawn": {},
            "guided-strike": {},
        },
    },
    "lay-on-hands": {"slot": "action"},
    "divine-smite": {"slot": "free"},
    "bardic-inspiration": {"slot": "bonus"},
    "flurry-of-blows": {"slot": "bonus"},
    "patient-defense": {"slot": "bonus"},
    "step-of-the-wind": {"slot": "bonus"},
    "wild-shape": {"slot": "action"},
    "rage": {"slot": "bonus"},
    "reckless-attack": {"slot": "free"},
    "quickened-spell": {"slot": "bonus"},
}


def _feature_economy_slot(feature_key: str, option_key: str | None) -> str | None:
    """Resolve (feature, option) to a slot using the curated table.

    Returns "action" / "bonus" / "reaction" / "free", or None when the
    feature isn't in the table. Option slot can override the parent's;
    if the option doesn't specify, the parent's slot wins. Unknown
    options return the parent's slot (the picker treats a no-match as
    "any of the listed options", same as the JS lookup).
    """
    feat = _FEATURE_ECONOMY.get((feature_key or "").lower())
    if not feat:
        return None
    parent_slot = feat.get("slot")
    if option_key:
        opt = (feat.get("options") or {}).get(option_key.lower())
        if opt and opt.get("slot"):
            return opt["slot"]
    return parent_slot


def _is_slot_used(campaign_id: int, character_id: int, slot: str) -> bool:
    """Look up the current battle state and return True if ``character_id``'s
    ``slot`` chip is already burnt. Used by Phase 4 over-budget gating to
    decide whether a player click needs a Layer B confirm modal. False on
    "free" / "movement" / "none" / unknown slots, or when no battle is
    active or the character isn't in init.
    """
    if slot not in ("action", "bonus", "reaction"):
        return False
    state = hub.get_battle(campaign_id)
    if not state:
        return False
    for c in state.get("combatants") or []:
        if c.get("char_id") == character_id:
            economy = c.get("economy") or {}
            return bool(economy.get(slot))
    return False


async def _mark_battle_economy(campaign_id: int, character_id: int, slot: str) -> None:
    """Mark a PC's action-economy slot in the hub battle state.

    No-op when the campaign has no active battle, the character isn't in
    init, the slot is invalid, or the slot is already used (matches the
    JS ``_markCombatantEconomy`` idempotence — clicking Strike twice
    doesn't free up your action). Broadcasts ``economy_update`` so every
    connected tabletop client (GM included — GM ignores ``battle_update``
    but listens to this) updates its chip strip.
    """
    if slot not in ("action", "bonus", "reaction"):
        return
    state = hub.get_battle(campaign_id)
    if not state:
        return
    target = None
    for c in state.get("combatants") or []:
        if c.get("char_id") == character_id:
            target = c
            break
    if target is None:
        return
    economy = target.get("economy")
    if not isinstance(economy, dict):
        economy = {"action": False, "bonus": False, "reaction": False, "movement": 0}
        target["economy"] = economy
    if economy.get(slot):
        return
    economy[slot] = True
    hub.set_battle(campaign_id, state)
    await hub.broadcast(campaign_id, {
        "type": "economy_update",
        "data": {"character_id": character_id, "slot": slot, "used": True},
    })


# ----------- helpers -----------

def _user_can_view_campaign(db: Session, user: User, campaign: Campaign) -> bool:
    if user.is_admin:
        return True
    if campaign.gm_user_id == user.id:
        return True
    member = (
        db.query(CampaignMembership)
        .filter(
            CampaignMembership.campaign_id == campaign.id,
            CampaignMembership.user_id == user.id,
        )
        .first()
    )
    return member is not None


def _user_is_gm(user: User, campaign: Campaign, db: Optional[Session] = None) -> bool:
    """True if `user` has GM powers in `campaign`.

    Sources of GM rights, in order of cost: site admin (free, no DB), primary
    GM/owner (free, no DB), or co-GM (membership row with is_gm=True; needs db).
    """
    if user.is_admin:
        return True
    if campaign.gm_user_id == user.id:
        return True
    if db is None:
        return False
    co_gm = (
        db.query(CampaignMembership)
        .filter(
            CampaignMembership.campaign_id == campaign.id,
            CampaignMembership.user_id == user.id,
            CampaignMembership.is_gm == True,  # noqa: E712
        )
        .first()
    )
    return co_gm is not None


def _user_is_primary_gm(user: User, campaign: Campaign) -> bool:
    return campaign.gm_user_id == user.id


def _user_can_move_token(db: Session, user: User, token: Token, campaign: Campaign) -> bool:
    if _user_is_gm(user, campaign, db):
        return True
    if token.is_hidden:
        return False
    if token.controller_user_id is not None and token.controller_user_id == user.id:
        return True
    if token.character_id is None:
        return False
    char = db.query(Character).filter(Character.id == token.character_id).first()
    return char is not None and char.owner_user_id == user.id


def _filter_roll_for_user(roll: DiceRoll, user: User, campaign: Campaign, db: Optional[Session] = None) -> bool:
    if _user_is_gm(user, campaign, db):
        return True
    if roll.visibility == Visibility.PUBLIC:
        return True
    if roll.visibility == Visibility.GM_AND_ROLLER:
        return roll.user_id == user.id
    return False


def _build_user_maps(db: Session, campaign: Campaign):
    """Return (user_color_map, user_portrait_map, user_char_name_map) for a campaign.

    user_color_map    : {user_id: hex_color_str}  — char color if set, else player color
    user_portrait_map : {user_id: portrait_url}   — first character portrait per user
    user_char_name_map: {user_id: char_name}       — first character name per user
    """
    # Start with player-level colors from memberships and GM
    memberships = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign.id)
        .all()
    )
    user_color_map: dict[int, str] = {}
    for m in memberships:
        if m.color:
            user_color_map[m.user_id] = m.color
    if campaign.gm_color:
        user_color_map[campaign.gm_user_id] = campaign.gm_color

    # Characters: first per user wins for name/portrait; char color overrides player color
    chars = (
        db.query(Character)
        .filter(
            Character.campaign_id == campaign.id,
            Character.owner_user_id.isnot(None),
        )
        .all()
    )
    user_portrait_map: dict[int, str] = {}
    user_char_name_map: dict[int, str] = {}
    for c in chars:
        uid = c.owner_user_id
        if uid not in user_char_name_map:
            # First character per user wins
            user_char_name_map[uid] = c.name
            if c.portrait_url:
                user_portrait_map[uid] = c.portrait_url
            if c.color:
                user_color_map[uid] = c.color  # char color overrides player color
        elif c.color and uid not in user_portrait_map:
            # Still might pick up portrait from a later char if first had none
            if c.portrait_url:
                user_portrait_map[uid] = c.portrait_url

    return user_color_map, user_portrait_map, user_char_name_map


# ----------- pages -----------

@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    primary_gm_campaigns = db.query(Campaign).filter(Campaign.gm_user_id == user.id).all()
    co_gm_memberships = (
        db.query(CampaignMembership)
        .filter(
            CampaignMembership.user_id == user.id,
            CampaignMembership.is_gm == True,  # noqa: E712
        )
        .all()
    )
    co_gm_ids = [m.campaign_id for m in co_gm_memberships]
    co_gm_campaigns = (
        db.query(Campaign).filter(Campaign.id.in_(co_gm_ids)).all() if co_gm_ids else []
    )
    seen = {c.id for c in primary_gm_campaigns}
    gm_campaigns = primary_gm_campaigns + [c for c in co_gm_campaigns if c.id not in seen]
    player_member_ids = [
        m.campaign_id
        for m in db.query(CampaignMembership)
        .filter(
            CampaignMembership.user_id == user.id,
            CampaignMembership.is_gm == False,  # noqa: E712
        )
        .all()
    ]
    member_campaigns = (
        db.query(Campaign).filter(Campaign.id.in_(player_member_ids)).all() if player_member_ids else []
    )
    if user.is_admin:
        all_campaigns = db.query(Campaign).all()
    else:
        all_campaigns = []
    gm_names = {
        c.id: (
            db.query(User).filter(User.id == c.gm_user_id).first().display_name
            if db.query(User).filter(User.id == c.gm_user_id).first()
            else "?"
        )
        for c in member_campaigns + all_campaigns
    }
    return templates.TemplateResponse(
        "lobby.html",
        {
            "request": request,
            "user": user,
            "gm_campaigns": gm_campaigns,
            "member_campaigns": member_campaigns,
            "all_campaigns": all_campaigns,
            "gm_names": gm_names,
            "system_choices": system_choices(),
            "get_system": get_system,
        },
    )


@router.post("/campaigns")
async def create_campaign(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    game_system: str = Form("generic"),
    thumbnail: UploadFile = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    sys = get_system(game_system)
    c = Campaign(
        name=name.strip(),
        description=description.strip(),
        gm_user_id=user.id,
        game_system=sys.key,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    if thumbnail and thumbnail.filename:
        from ..routes.admin_routes import _save_thumbnail
        c.thumbnail_url = await _save_thumbnail(thumbnail)
        db.commit()
    m = Map(campaign_id=c.id, name="Default map")
    db.add(m)
    db.commit()
    db.refresh(m)
    c.active_map_id = m.id
    db.commit()
    return RedirectResponse(f"/campaign/{c.id}", status_code=303)


@router.get("/campaign/{campaign_id}", response_class=HTMLResponse)
def campaign_view(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    view_as: Optional[int] = Query(None),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member of this campaign")
    is_gm = _user_is_gm(user, campaign, db)

    # GM preview mode: render the tabletop as if the requester were a specific player.
    view_as_user = None
    if view_as and is_gm:
        target = db.query(User).filter(User.id == view_as).first()
        if target and _user_can_view_campaign(db, target, campaign):
            view_as_user = user          # keep real GM reference for the banner
            user = target                # override user context for template rendering
            is_gm = False

    # Session gate: players (non-GM members) only see the tabletop while the
    # GM has the session active. They get a "waiting" page that auto-redirects
    # via WebSocket the moment the GM hits Start.
    if not is_gm and not view_as_user and not campaign.session_active:
        return templates.TemplateResponse(
            "session_waiting.html",
            {
                "request": request,
                "user": user,
                "campaign": campaign,
            },
        )
    active_map = (
        db.query(Map).filter(Map.id == campaign.active_map_id).first()
        if campaign.active_map_id
        else None
    )
    tokens = (
        db.query(Token).filter(Token.map_id == active_map.id).all() if active_map else []
    )
    characters = db.query(Character).filter(Character.campaign_id == campaign.id).all()
    # Normalize D&D 5e sheets so the tabletop mini-sheet sees a multiclass-aware
    # ``classes`` roster + nested ``spell_slots`` even on legacy data.
    for _ch in characters:
        if _ch.template == "dnd5e" and isinstance(_ch.sheet, dict):
            normalize_dnd5e_sheet(_ch.sheet)
    rolls = (
        db.query(DiceRoll)
        .filter(DiceRoll.campaign_id == campaign.id)
        .order_by(DiceRoll.created_at.desc())
        .limit(100)
        .all()
    )
    visible_rolls = list(reversed([r for r in rolls if _filter_roll_for_user(r, user, campaign, db)]))
    members = (
        db.query(User)
        .join(CampaignMembership, CampaignMembership.user_id == User.id)
        .filter(CampaignMembership.campaign_id == campaign.id)
        .all()
    )
    # Audio context: currently-playing track (if any) so reconnecting clients
    # immediately resume on page load. started_at_ms is sent so the client
    # can compute the seek offset and stay in sync with everyone else.
    now_playing = (
        db.query(PlaylistTrack).filter(PlaylistTrack.id == campaign.now_playing_track_id).first()
        if campaign.now_playing_track_id
        else None
    )
    now_playing_started_at_ms = None
    if now_playing and campaign.now_playing_started_at:
        now_playing_started_at_ms = int(
            campaign.now_playing_started_at.replace(tzinfo=timezone.utc).timestamp() * 1000
        )
    playlists = (
        db.query(Playlist)
        .filter(Playlist.campaign_id == campaign.id)
        .order_by(Playlist.id)
        .all()
        if is_gm
        else []
    )
    # All maps in the campaign — surfaced for the Encounters panel's map
    # dropdown in the Save / Edit forms. GM-only (the panel itself is
    # gated), so we skip the query for non-GMs.
    all_maps = (
        db.query(Map)
        .filter(Map.campaign_id == campaign.id)
        .order_by(Map.id)
        .all()
        if is_gm
        else []
    )
    tmpl_objs = db.query(TokenTemplate).filter(TokenTemplate.campaign_id == campaign.id).order_by(TokenTemplate.name).all()
    char_data = [
        {
            "id": c.id,
            "name": c.name,
            "owner_user_id": c.owner_user_id,
            "template": c.template,
            "sheet": c.sheet or {},
            # Surfaced for the GM's "Players" tab in the Add Token modal —
            # mini-sheet rendering already pulls portrait/color from the
            # user_*_map helpers, so these fields cover the per-character
            # avatar in the picker without duplicating the merge logic.
            "portrait_url": c.portrait_url,
            "color": c.color,
            "ring_style": c.ring_style,
        }
        for c in characters
    ]
    token_data = [_token_dict(t) for t in tokens]
    # v2.3.34: each template's ``sheet`` is pre-resolved through the
    # monster adapter so the client-side init-tracker reads real stats
    # (HP / AC / abilities / structured actions) instead of the minimal
    # ``_npc_sheet`` slug-pointer placeholders (``abilities={STR:10,...}``)
    # the demo seeds. For non-monster templates the adapter returns the
    # input sheet unchanged so this is a no-op. Replaces the v2.3.17
    # ``monster_templates`` context which built a hidden pool of
    # synthesized PC-style mini-sheets — the user preferred the older
    # 2.3.9 inline stat-block view that ``buildMonsterInitSheet``
    # produces directly from this resolved sheet.
    tmpl_data = []
    for t in tmpl_objs:
        raw_sheet = t.sheet or {}
        if (t.template or "dnd5e") == "dnd5e":
            try:
                resolved = _monster_template_to_sheet(t, campaign.id)
            except Exception:  # noqa: BLE001
                resolved = raw_sheet
        else:
            resolved = raw_sheet
        tmpl_data.append({
            "id": t.id,
            "name": t.name,
            "image_url": t.image_url,
            "tags": t.tags or [],
            "template": t.template,
            "sheet": resolved,
        })

    user_color_map, user_portrait_map, user_char_name_map = _build_user_maps(db, campaign)
    conc_effects = db.query(ConcentrationEffect).filter(ConcentrationEffect.campaign_id == campaign_id).all()
    conc_by_char = {
        e.character_id: {
            "id": e.id,
            "spell_name": e.spell_name,
            "rounds_remaining": e.rounds_remaining,
            "notes": e.notes or "",
        }
        for e in conc_effects
    }
    return templates.TemplateResponse(
        "tabletop.html",
        {
            "request": request,
            "user": user,
            "is_gm": is_gm,
            "campaign": campaign,
            "active_map": active_map,
            "tokens": tokens,
            "characters": characters,
            "members": members,
            "rolls": visible_rolls,
            "settings": get_settings(),
            "system": get_system(campaign.game_system),
            "now_playing": now_playing,
            "now_playing_started_at_ms": now_playing_started_at_ms,
            "playlists": playlists,
            "all_maps": all_maps,
            "char_data": char_data,
            "token_data": token_data,
            "tmpl_data": tmpl_data,
            "user_color_map": user_color_map,
            "user_portrait_map": user_portrait_map,
            "user_char_name_map": user_char_name_map,
            "conc_by_char": conc_by_char,
            "hp_thresholds": campaign.hp_thresholds or _DEFAULT_HP_THRESHOLDS,
            "view_as_user": view_as_user,
        },
    )


@router.get("/campaign/{campaign_id}/settings", response_class=HTMLResponse)
def campaign_settings(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM-accessible settings page (also reachable by admins)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    member_rows = (
        db.query(CampaignMembership, User)
        .join(User, User.id == CampaignMembership.user_id)
        .filter(CampaignMembership.campaign_id == campaign_id)
        .all()
    )
    members_with_role = [
        {"user": u, "is_gm": m.is_gm, "membership_id": m.id, "color": m.color or ""} for m, u in member_rows
    ]
    member_user_ids = {m["user"].id for m in members_with_role}
    primary_gm = db.query(User).filter(User.id == campaign.gm_user_id).first()
    all_users = db.query(User).order_by(User.display_name).all()
    non_members = [
        u for u in all_users
        if u.id not in member_user_ids and u.id != campaign.gm_user_id
    ]
    characters = (
        db.query(Character)
        .filter(Character.campaign_id == campaign_id)
        .order_by(Character.name)
        .all()
    )
    maps = db.query(Map).filter(Map.campaign_id == campaign_id).order_by(Map.id).all()
    playlists = (
        db.query(Playlist)
        .filter(Playlist.campaign_id == campaign_id)
        .order_by(Playlist.id)
        .all()
    )
    tmpl_objs = db.query(TokenTemplate).filter(TokenTemplate.campaign_id == campaign_id).order_by(TokenTemplate.name).all()
    # v2.0.0: file-based subclasses. The file's `slug` field carries the
    # combined `<class>__<sub>` form so each entry is addressable by a single
    # path-safe key. We also expose split `class_slug` / `sub_slug` for the
    # template form's existing field names.
    _subclass_records, _ = local_content.search(
        type="subclass_features", campaign_id=campaign_id, limit=500,
    )
    custom_subclasses = []
    for _r in _subclass_records:
        if _r.get("_source") != "local-homebrew":
            continue
        _combined = _r.get("slug") or ""
        if "__" in _combined:
            _cls, _, _sub = _combined.partition("__")
        else:
            _cls, _sub = _r.get("class_slug") or "", _combined
        custom_subclasses.append({
            **_r,
            "class_slug": _cls,
            "sub_slug": _sub,
            "combined_slug": _combined,
        })
    # Match the legacy ORM ordering: by parent class, then by subclass name.
    custom_subclasses.sort(key=lambda r: (r.get("class_slug") or "", (r.get("name") or "").lower()))
    # v2.0.0: file-based class_features. Project the homebrew records back to
    # the legacy template field names (``class_slug``) so the existing edit
    # form keeps working without template changes; the schema types
    # ``features`` as Any so the editor's structured list round-trips.
    _class_records, _ = local_content.search(
        type="class_features", campaign_id=campaign_id, limit=500,
    )
    custom_classes = []
    for _c in _class_records:
        if _c.get("_source") != "local-homebrew":
            continue
        custom_classes.append({
            **_c,
            "class_slug": _c.get("slug"),  # template legacy alias
        })
    custom_classes.sort(key=lambda r: (r.get("name") or "").lower())
    # v2.0.0: file-based races.
    custom_races, _ = local_content.search(
        type="races", campaign_id=campaign_id, limit=500,
    )
    # v2.0.0: file-based monsters. The Pydantic Monster model stores a single
    # `actions: list[Action]` array with a `category` discriminator; the
    # template's edit form expects the 4 legacy split lists. We split here so
    # the per-textarea editor populates correctly.
    _monster_records, _ = local_content.search(
        type="monsters", campaign_id=campaign_id, limit=500,
    )
    custom_monsters = []
    for _m in _monster_records:
        if _m.get("_source") != "local-homebrew":
            continue
        # Split unified actions back into category buckets for the template.
        # v2.3.8: also pass through the structured attack fields so the editor
        # can re-render them after a save (otherwise the next form load would
        # show them blank and a subsequent save would silently drop them).
        _by_cat: dict[str, list] = {"action": [], "reaction": [], "special_ability": [], "legendary_action": []}
        for _a in _m.get("actions") or []:
            _cat = (_a.get("category") or "action")
            if _cat in _by_cat:
                _entry = {"name": _a.get("name"), "desc": _a.get("desc"), "level": _a.get("min_level")}
                for _k in ("attack_roll", "attack_bonus", "damage", "damage_type",
                           "save_ability", "save_dc"):
                    _v = _a.get(_k)
                    if _v not in (None, "", False, 0):
                        _entry[_k] = _v
                _by_cat[_cat].append(_entry)
        custom_monsters.append({
            **_m,
            "monster_slug": _m.get("slug"),  # template legacy alias
            # Split actions for the 4-textarea form:
            "actions_split": _by_cat["action"],
            "reactions": _by_cat["reaction"],
            "special_abilities": _by_cat["special_ability"],
            "legendary_actions": _by_cat["legendary_action"],
        })
    custom_monsters.sort(key=lambda r: (r.get("name") or "").lower())
    # v2.0.0: file-based backgrounds (see custom_feats above for the pattern).
    custom_backgrounds, _ = local_content.search(
        type="backgrounds", campaign_id=campaign_id, limit=500,
    )
    # File-based homebrew at v2.0.0: feats live as JSON files under the
    # homebrew Docker volume rather than rows in custom_feats. The records
    # carry the same display fields the template expects (name, prerequisite,
    # desc) plus the new `slug` field (replacing the legacy int `id` for URL
    # addressing). See app/local_content.py for the resolver.
    custom_feats, _custom_feats_total = local_content.search(
        type="feats", campaign_id=campaign_id, limit=500,
    )
    # ── Encounters (Phase 1, v0.64.0) ────────────────────────────────────
    # Read-only listing of saved encounters; save / load / edit / delete
    # land in later phases. See docs/encounters-plan.md.
    encounters = (
        db.query(Encounter)
        .filter(Encounter.campaign_id == campaign_id)
        .order_by(Encounter.created_at.desc())
        .all()
    )

    # ── Audio history (PR 4) ─────────────────────────────────────────────
    # Recent plays (last 50, newest first), top tracks (by play count,
    # top 10), and a summary line. The table grows by ~1 row per track
    # play so capping the page render is important.
    from sqlalchemy import func
    audio_recent = (
        db.query(AudioPlayEvent)
        .filter(AudioPlayEvent.campaign_id == campaign_id)
        .order_by(AudioPlayEvent.started_at.desc())
        .limit(50)
        .all()
    )
    # Aggregate by the snapshot ``track_name`` so renamed/deleted tracks
    # still group correctly (the FK can be NULL after a delete).
    audio_top_rows = (
        db.query(
            AudioPlayEvent.track_name,
            func.count(AudioPlayEvent.id).label("play_count"),
            func.coalesce(func.sum(AudioPlayEvent.duration_s), 0).label("total_s"),
        )
        .filter(AudioPlayEvent.campaign_id == campaign_id)
        .filter(AudioPlayEvent.track_name != "")
        .group_by(AudioPlayEvent.track_name)
        .order_by(func.count(AudioPlayEvent.id).desc())
        .limit(10)
        .all()
    )
    audio_top = [
        {"track_name": r.track_name, "play_count": r.play_count, "total_s": int(r.total_s or 0)}
        for r in audio_top_rows
    ]
    audio_summary = (
        db.query(
            func.count(AudioPlayEvent.id).label("total"),
            func.coalesce(func.sum(AudioPlayEvent.duration_s), 0).label("total_s"),
        )
        .filter(AudioPlayEvent.campaign_id == campaign_id)
        .first()
    )
    audio_stats = {
        "total_plays": int(audio_summary.total or 0) if audio_summary else 0,
        "total_seconds": int(audio_summary.total_s or 0) if audio_summary else 0,
    }

    # Characters owned by campaign members (from any campaign) that aren't already here
    all_member_ids = list(member_user_ids | {campaign.gm_user_id})
    existing_char_ids = {c.id for c in characters}
    importable_chars = (
        db.query(Character)
        .filter(Character.owner_user_id.in_(all_member_ids))
        .filter(Character.campaign_id != campaign_id)
        .order_by(Character.name)
        .all()
    ) if all_member_ids else []

    # Annotate with owner display name for the template
    user_map = {u.id: u for u in all_users}
    importable = [
        {"char": c, "owner_name": user_map.get(c.owner_user_id, None)}
        for c in importable_chars
    ]

    return templates.TemplateResponse(
        "campaign_settings.html",
        {
            "request": request,
            "user": user,
            "campaign": campaign,
            "system_choices": system_choices(),
            "current_system": get_system(campaign.game_system),
            "members_with_role": members_with_role,
            "primary_gm": primary_gm,
            "all_users": all_users,
            "non_members": non_members,
            "characters": characters,
            "maps": maps,
            "playlists": playlists,
            "templates": tmpl_objs,
            "importable": importable,
            "custom_subclasses": custom_subclasses,
            "custom_classes": custom_classes,
            "custom_races": custom_races,
            "custom_monsters": custom_monsters,
            "custom_backgrounds": custom_backgrounds,
            "custom_feats": custom_feats,
            "audio_recent": audio_recent,
            "audio_top": audio_top,
            "audio_stats": audio_stats,
            "encounters": encounters,
            "hp_thresholds": campaign.hp_thresholds or _DEFAULT_HP_THRESHOLDS,
        },
    )


_VALID_CAMPAIGN_FONTS = {"", "lora", "cormorant", "im-fell"}

_DEFAULT_HP_THRESHOLDS = [
    {"label": "Healthy",  "min_pct": 76},
    {"label": "Wounded",  "min_pct": 51},
    {"label": "Bloodied", "min_pct": 26},
    {"label": "Critical", "min_pct": 1},
    {"label": "Dead",     "min_pct": 0},
]


@router.post("/campaign/{campaign_id}/settings")
async def campaign_settings_save(
    campaign_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    game_system: str = Form("generic"),
    gm_tab_color: str = Form(""),
    font_override: str = Form(""),
    auto_play_playlist_id: str = Form(""),
    auto_play_mode: str = Form("order"),
    default_encounter_id: str = Form(""),
    thumbnail: UploadFile = File(None),
    clear_thumbnail: bool = Form(False),
    hp_threshold_0: str = Form(""),
    hp_threshold_1: str = Form(""),
    hp_threshold_2: str = Form(""),
    hp_threshold_3: str = Form(""),
    hp_threshold_4: str = Form(""),
    # v2.5.0: house-rule toggles. Each one's a bool that defaults False
    # if the checkbox isn't checked (HTML form idiom: unchecked checkbox
    # doesn't submit the field). ``Form(False)`` recovers the default.
    potions_as_bonus_action: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404)
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    campaign.name = name.strip()[:120] or campaign.name
    campaign.description = description.strip()
    campaign.game_system = get_system(game_system).key
    campaign.gm_tab_color = gm_tab_color.strip()[:20] or None
    fo = font_override.strip()
    campaign.font_override = fo if fo in _VALID_CAMPAIGN_FONTS and fo else None
    # v2.5.0: house rules
    campaign.potions_as_bonus_action = potions_as_bonus_action
    # Default-encounter-on-session-start setting. Validate the encounter
    # belongs to this campaign before assigning; empty / invalid clears.
    de_raw = (default_encounter_id or "").strip()
    if de_raw:
        try:
            de_id = int(de_raw)
        except ValueError:
            de_id = None
        if de_id:
            owned = (
                db.query(Encounter.id)
                .filter(Encounter.id == de_id, Encounter.campaign_id == campaign_id)
                .first()
            )
            campaign.default_encounter_id = owned[0] if owned else None
        else:
            campaign.default_encounter_id = None
    else:
        campaign.default_encounter_id = None
    # Audio auto-start config. Empty value = no auto-play. Validate the
    # playlist belongs to this campaign before assigning.
    ap_raw = (auto_play_playlist_id or "").strip()
    if ap_raw:
        try:
            ap_id = int(ap_raw)
        except ValueError:
            ap_id = None
        if ap_id:
            owned = (
                db.query(Playlist.id)
                .filter(Playlist.id == ap_id, Playlist.campaign_id == campaign_id)
                .first()
            )
            campaign.auto_play_playlist_id = owned[0] if owned else None
        else:
            campaign.auto_play_playlist_id = None
    else:
        campaign.auto_play_playlist_id = None
    mode = (auto_play_mode or "order").strip().lower()
    campaign.auto_play_mode = "shuffle" if mode == "shuffle" else "order"
    if clear_thumbnail:
        campaign.thumbnail_url = None
    if thumbnail and thumbnail.filename:
        from ..routes.admin_routes import _save_thumbnail
        campaign.thumbnail_url = await _save_thumbnail(thumbnail)
    raw_labels = [hp_threshold_0, hp_threshold_1, hp_threshold_2, hp_threshold_3, hp_threshold_4]
    if any(l.strip() for l in raw_labels):
        new_thresholds = []
        for i, (default, label) in enumerate(zip(_DEFAULT_HP_THRESHOLDS, raw_labels)):
            new_thresholds.append({
                "label": label.strip()[:40] or default["label"],
                "min_pct": default["min_pct"],
            })
        campaign.hp_thresholds = new_thresholds
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings", status_code=303)


# ── Custom subclasses (GM-authored homebrew) ─────────────────────────────────
#
# GM-only CRUD for rows in the ``custom_subclasses`` table introduced in
# v0.42.0.  The resolver in app/local_features.py picks these up under
# scope ``campaign:<id>`` and returns them in place of the shipped global
# SRD content when a player opens a subclass detail panel for a character
# in this campaign.

import re as _re_csub

_SLUG_CLEAN = _re_csub.compile(r"[^a-z0-9]+")


def _slugify_for_subclass(value: str, max_len: int = 80) -> str:
    """Lowercase, replace runs of non-alphanumerics with single dashes, trim.

    Used for both the parent class slug (e.g. "Fighter" -> "fighter") and
    the subclass slug derived from its display name (e.g. "Circle of the
    Deep" -> "circle-of-the-deep").
    """
    s = (value or "").strip().lower()
    s = _SLUG_CLEAN.sub("-", s).strip("-")
    return s[:max_len]


def _parse_custom_subclass_features(raw: str, *, extra_keys: tuple[str, ...] = ()) -> list:
    """Parse and normalise the features JSON textarea.

    Required shape::

        [
          {"name": "Combat Wild Shape", "level": 2, "desc": "..."},
          {"name": "Primal Strike",     "level": 6, "desc": "..."}
        ]

    ``level`` may be null/missing. ``desc`` may be empty. Raises
    ``HTTPException(400, ...)`` with a human-readable message on any
    structural problem so the form can render it back to the GM.

    ``extra_keys`` (v2.3.8): names of optional additional keys to preserve
    verbatim from each input dict. Used by the monster-actions coalescer
    to pass through the structured attack fields (``attack_roll``,
    ``attack_bonus``, ``damage``, ``damage_type``, ``save_ability``,
    ``save_dc``) that the action-mode editor now emits. Default empty
    tuple keeps the strict feature/trait behavior unchanged.
    """
    if not raw or not raw.strip():
        return []
    import json as _json
    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError as e:
        raise HTTPException(400, f"Features JSON: invalid syntax — {e.msg} (line {e.lineno})")
    if not isinstance(parsed, list):
        raise HTTPException(
            400,
            'Features JSON: must be a list, e.g. [{"name":"...","level":2,"desc":"..."}]',
        )
    out: list = []
    for i, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            raise HTTPException(400, f"Features JSON: entry #{i} must be an object")
        name = (item.get("name") or "").strip()
        if not name:
            raise HTTPException(400, f"Features JSON: entry #{i} is missing a non-empty 'name'")
        lvl_raw = item.get("level")
        if lvl_raw is None or lvl_raw == "":
            level_norm: int | None = None
        else:
            try:
                level_norm = int(lvl_raw)
            except (TypeError, ValueError):
                raise HTTPException(
                    400, f"Features JSON: entry #{i} 'level' must be an integer (got {lvl_raw!r})"
                )
        desc = (item.get("desc") or "").strip()
        rec: dict = {"name": name[:160], "level": level_norm, "desc": desc[:4000]}
        for ek in extra_keys:
            if ek in item:
                rec[ek] = item[ek]
        out.append(rec)
    return out


def _require_gm_for_campaign(campaign_id: int, user: User, db: Session) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    return campaign


@router.post("/campaign/{campaign_id}/custom-subclasses")
def create_custom_subclass(
    campaign_id: int,
    name: str = Form(...),
    class_slug: str = Form(...),
    flavor: str = Form(""),
    features_json: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_gm_for_campaign(campaign_id, user, db)
    name_n = (name or "").strip()[:120]
    cls_slug = _slugify_for_subclass(class_slug, max_len=60)
    sub_slug = _slugify_for_subclass(name_n)
    if not name_n:
        raise HTTPException(400, "Name is required")
    if not cls_slug:
        raise HTTPException(400, "Parent class is required")
    if not sub_slug:
        raise HTTPException(400, "Name does not yield a valid slug — use letters or numbers")
    features = _parse_custom_subclass_features(features_json)

    combined = f"{cls_slug}__{sub_slug}"
    existing = local_content.resolve(combined, type="subclass_features", campaign_id=campaign_id)
    if existing and existing[1] == "local-homebrew":
        raise HTTPException(
            400,
            f"A homebrew subclass with slug '{sub_slug}' already exists for class '{cls_slug}' in this campaign",
        )
    try:
        local_content.write_homebrew(
            {
                "slug": combined,
                "name": name_n,
                "class_slug": cls_slug,
                "subclass_flavor": (flavor or "").strip()[:4000],
                "features": features,
                "actions": [],
                "system": "dnd5e",
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
                "owner": user.id,
            },
            type="subclass_features",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-subclasses", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-subclasses/{combined_slug}")
def update_custom_subclass(
    campaign_id: int,
    combined_slug: str,
    name: str = Form(...),
    class_slug: str = Form(...),
    flavor: str = Form(""),
    features_json: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based subclass update. ``combined_slug`` is the file's
    `<class>__<sub>` identifier. Reassigning the parent class effectively
    means moving to a new file path; we write the new file under the new
    combined slug and delete the old file."""
    _require_gm_for_campaign(campaign_id, user, db)
    hit = local_content.resolve(combined_slug, type="subclass_features", campaign_id=campaign_id)
    if not hit or hit[1] != "local-homebrew":
        raise HTTPException(404, "Custom subclass not found")
    existing = hit[0]

    name_n = (name or "").strip()[:120]
    new_cls = _slugify_for_subclass(class_slug, max_len=60)
    if not name_n:
        raise HTTPException(400, "Name is required")
    if not new_cls:
        raise HTTPException(400, "Parent class is required")
    features = _parse_custom_subclass_features(features_json)

    old_cls, _, old_sub = combined_slug.partition("__")
    if not old_sub:
        old_sub = combined_slug  # legacy file without class prefix
    new_combined = f"{new_cls}__{old_sub}"

    if new_combined != combined_slug:
        # Class reassignment: would the new combined slug collide with another
        # homebrew under the same campaign? Reject rather than overwrite.
        collision = local_content.resolve(new_combined, type="subclass_features", campaign_id=campaign_id)
        if collision and collision[1] == "local-homebrew":
            raise HTTPException(
                400,
                f"Class '{new_cls}' already has a homebrew subclass with slug '{old_sub}'",
            )

    try:
        local_content.write_homebrew(
            {
                **existing,
                "slug": new_combined,
                "name": name_n,
                "class_slug": new_cls,
                "subclass_flavor": (flavor or "").strip()[:4000],
                "features": features,
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
            },
            type="subclass_features",
            scope=f"campaign-{campaign_id}",
        )
        # Remove the old file if the combined slug changed (class reassignment).
        if new_combined != combined_slug:
            local_content.delete_homebrew(
                combined_slug, type="subclass_features", scope=f"campaign-{campaign_id}",
            )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-subclasses", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-subclasses/{combined_slug}/delete")
def delete_custom_subclass(
    campaign_id: int,
    combined_slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based subclass delete by combined `<class>__<sub>` slug."""
    _require_gm_for_campaign(campaign_id, user, db)
    try:
        removed = local_content.delete_homebrew(
            combined_slug, type="subclass_features", scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not removed:
        raise HTTPException(404, "Custom subclass not found")
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-subclasses", status_code=303
    )


# ── Custom classes (GM-authored homebrew base classes) ───────────────────────
#
# Mirror of the custom-subclass routes above but for the parent class itself.
# Slug is fixed at creation (character sheets reference it); proficiency
# fields are bounded strings; features re-use the same JSON shape parser as
# subclasses.  MVP scope: no spell list, no class-resource counters, no
# multiclass-prereq fields.

_VALID_SPELLCASTING_ABILITIES = {"", "str", "dex", "con", "int", "wis", "cha"}


def _normalize_spellcasting_ability(raw: str) -> str:
    v = (raw or "").strip().lower()
    if v not in _VALID_SPELLCASTING_ABILITIES:
        raise HTTPException(400, "Spellcasting ability must be one of: str, dex, con, int, wis, cha (or blank)")
    return v


def _normalize_hit_die(raw) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(400, "Hit die must be an integer between 4 and 12")
    if n < 4 or n > 12:
        raise HTTPException(400, "Hit die must be between 4 and 12")
    return n


_ABILITY_KEYS = ("str", "dex", "con", "int", "wis", "cha")


def _parse_multiclass_prereq_abilities(values: dict) -> dict:
    """Coerce six ability-minimum form fields into a clean ``{ability: int}``
    dict.  Empty strings are dropped (no requirement on that ability).
    Pass in ``{"str": form_str, "dex": form_dex, …}``.
    """
    out: dict = {}
    for ab, raw in values.items():
        v = (raw or "").strip()
        if not v:
            continue
        try:
            n = int(v)
        except ValueError:
            raise HTTPException(400, f"Multiclass prereq for {ab.upper()} must be an integer (got {raw!r})")
        if n < 1 or n > 30:
            raise HTTPException(400, f"Multiclass prereq for {ab.upper()} must be between 1 and 30")
        out[ab] = n
    return out


def _normalize_multiclass_mode(raw: str) -> str:
    v = (raw or "all").strip().lower()
    if v not in ("all", "any"):
        raise HTTPException(400, "Multiclass mode must be 'all' or 'any'")
    return v


_VALID_RESOURCE_KINDS = {"static", "ability_mod", "proficiency", "level_table"}
_VALID_RESOURCE_RESETS = {"short", "long", "none"}


def _parse_class_resources_json(raw: str) -> list:
    """Parse and normalise the resources JSON field on the custom class form.

    Each entry shape::

        {
          "key": "channel-divinity",          # optional — auto-derived from name
          "name": "Channel Divinity",
          "min_level": 2,
          "max_kind": "static" | "ability_mod" | "proficiency" | "level_table",
          "max_static": 1,                    # required when max_kind = "static"
          "max_ability": "cha",               # required when max_kind = "ability_mod"
          "max_table": {"2":1, "6":2, "18":3},# required when max_kind = "level_table"
          "reset": "short" | "long" | "none",
          "desc": "..."
        }

    Drops rows where ``name`` is empty (treated as an abandoned editor row).
    Generates a stable ``key`` from the name when one isn't provided, and
    dedupes by key so the frontend doesn't see two recipes with the same
    identifier (which would break its uses-tracking state).
    """
    if not raw or not raw.strip():
        return []
    import json as _json
    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError as e:
        raise HTTPException(400, f"Resources JSON: invalid syntax — {e.msg} (line {e.lineno})")
    if not isinstance(parsed, list):
        raise HTTPException(400, "Resources JSON: must be a list of resource objects")

    out: list = []
    used_keys: set[str] = set()
    for i, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            raise HTTPException(400, f"Resources JSON: entry #{i} must be an object")
        name = (item.get("name") or "").strip()
        if not name:
            continue  # quietly drop abandoned rows
        kind = (item.get("max_kind") or "static").strip().lower()
        if kind not in _VALID_RESOURCE_KINDS:
            raise HTTPException(
                400,
                f"Resources JSON: entry #{i} 'max_kind' must be one of {sorted(_VALID_RESOURCE_KINDS)}",
            )
        reset = (item.get("reset") or "long").strip().lower()
        if reset not in _VALID_RESOURCE_RESETS:
            raise HTTPException(
                400,
                f"Resources JSON: entry #{i} 'reset' must be one of {sorted(_VALID_RESOURCE_RESETS)}",
            )
        try:
            min_level = int(item.get("min_level", 1))
        except (TypeError, ValueError):
            raise HTTPException(400, f"Resources JSON: entry #{i} 'min_level' must be an integer")
        if min_level < 1 or min_level > 20:
            raise HTTPException(400, f"Resources JSON: entry #{i} 'min_level' must be between 1 and 20")

        rec: dict = {
            "name": name[:120],
            "min_level": min_level,
            "max_kind": kind,
            "reset": reset,
            "desc": (item.get("desc") or "").strip()[:1000],
        }

        if kind == "static":
            try:
                rec["max_static"] = int(item.get("max_static", 1))
            except (TypeError, ValueError):
                raise HTTPException(400, f"Resources JSON: entry #{i} 'max_static' must be an integer")
            if rec["max_static"] < 0 or rec["max_static"] > 999:
                raise HTTPException(400, f"Resources JSON: entry #{i} 'max_static' out of range")
        elif kind == "ability_mod":
            ab = (item.get("max_ability") or "").strip().lower()
            if ab not in ("str", "dex", "con", "int", "wis", "cha"):
                raise HTTPException(
                    400, f"Resources JSON: entry #{i} 'max_ability' must be one of str/dex/con/int/wis/cha"
                )
            rec["max_ability"] = ab
        elif kind == "level_table":
            tbl_raw = item.get("max_table") or {}
            if not isinstance(tbl_raw, dict):
                raise HTTPException(400, f"Resources JSON: entry #{i} 'max_table' must be an object")
            clean: dict = {}
            for k, v in tbl_raw.items():
                try:
                    kk = int(k)
                    vv = int(v)
                except (TypeError, ValueError):
                    raise HTTPException(
                        400, f"Resources JSON: entry #{i} 'max_table' must map integer level → integer count"
                    )
                if kk < 1 or kk > 20:
                    continue
                clean[str(kk)] = vv
            if not clean:
                raise HTTPException(400, f"Resources JSON: entry #{i} 'max_table' is empty")
            rec["max_table"] = clean
        # "proficiency" needs no extra fields.

        # Derive a stable key. Prefer explicit, then slugify the name, then
        # fall back to "resource-<index>" so we never collide on empty keys.
        key = (item.get("key") or "").strip().lower() or _slugify_for_subclass(name, max_len=60) or f"resource-{i}"
        if key in used_keys:
            key = f"{key}-{i}"
        used_keys.add(key)
        rec["key"] = key
        out.append(rec)

    return out[:50]  # cap so we don't let GMs paste hundreds


def _parse_spell_list_json(raw: str) -> list:
    """Parse + dedupe + normalise the spell_list JSON field on the custom
    class form. Accepts either a list of slug strings or a list of objects
    with a ``slug`` field (the picker emits the latter for convenience)."""
    if not raw or not raw.strip():
        return []
    import json as _json
    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError as e:
        raise HTTPException(400, f"Spell list JSON: invalid syntax — {e.msg} (line {e.lineno})")
    if not isinstance(parsed, list):
        raise HTTPException(400, 'Spell list JSON: must be a list of spell slugs')
    out: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(parsed, start=1):
        if isinstance(item, str):
            slug = item.strip().lower()
        elif isinstance(item, dict):
            slug = (item.get("slug") or "").strip().lower()
        else:
            raise HTTPException(400, f"Spell list entry #{i} must be a slug string or {{slug: ...}} object")
        if not slug:
            continue
        # Allow only lowercase letters / digits / dashes — matches Open5e slugs.
        if not _re_csub.match(r'^[a-z0-9-]+$', slug):
            raise HTTPException(400, f"Spell list entry #{i} contains invalid slug characters: {slug!r}")
        if slug in seen:
            continue
        seen.add(slug)
        out.append(slug)
    return out[:500]  # cap so we don't let GMs paste tens-of-thousands


@router.post("/campaign/{campaign_id}/custom-classes")
def create_custom_class(
    campaign_id: int,
    name: str = Form(...),
    hit_die: str = Form("8"),
    prof_armor: str = Form(""),
    prof_weapons: str = Form(""),
    prof_tools: str = Form(""),
    prof_saving_throws: str = Form(""),
    prof_skills: str = Form(""),
    spellcasting_ability: str = Form(""),
    equipment: str = Form(""),
    features_json: str = Form(""),
    spell_list_json: str = Form(""),
    resources_json: str = Form(""),
    mc_prereq_str: str = Form(""),
    mc_prereq_dex: str = Form(""),
    mc_prereq_con: str = Form(""),
    mc_prereq_int: str = Form(""),
    mc_prereq_wis: str = Form(""),
    mc_prereq_cha: str = Form(""),
    mc_prereq_mode: str = Form("all"),
    multiclass_proficiencies: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_gm_for_campaign(campaign_id, user, db)
    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    cls_slug = _slugify_for_subclass(name_n, max_len=60)
    if not cls_slug:
        raise HTTPException(400, "Name does not yield a valid slug — use letters or numbers")
    hd = _normalize_hit_die(hit_die)
    spc = _normalize_spellcasting_ability(spellcasting_ability)
    features = _parse_custom_subclass_features(features_json)
    spell_list = _parse_spell_list_json(spell_list_json)
    resources = _parse_class_resources_json(resources_json)
    mc_prereqs = _parse_multiclass_prereq_abilities({
        "str": mc_prereq_str, "dex": mc_prereq_dex, "con": mc_prereq_con,
        "int": mc_prereq_int, "wis": mc_prereq_wis, "cha": mc_prereq_cha,
    })
    mc_mode = _normalize_multiclass_mode(mc_prereq_mode)

    scope = f"campaign-{campaign_id}"
    existing = local_content.resolve(cls_slug, type="class_features", campaign_id=campaign_id)
    if existing and existing[1] == "local-homebrew":
        raise HTTPException(400, f"A homebrew class with slug '{cls_slug}' already exists in this campaign")

    local_content.write_homebrew(
        {
            "slug": cls_slug,
            "name": name_n,
            "hit_die": hd,
            "prof_armor": (prof_armor or "").strip()[:500],
            "prof_weapons": (prof_weapons or "").strip()[:500],
            "prof_tools": (prof_tools or "").strip()[:500],
            "prof_saving_throws": (prof_saving_throws or "").strip()[:120],
            "prof_skills": (prof_skills or "").strip()[:500],
            "spellcasting_ability": spc,
            "equipment": (equipment or "").strip()[:4000],
            "features": features,
            "spell_list": spell_list,
            "resources": resources,
            "multiclass_prereq_abilities": mc_prereqs,
            "multiclass_prereq_mode": mc_mode,
            "multiclass_proficiencies": (multiclass_proficiencies or "").strip()[:500],
            "actions": [],
            "system": "dnd5e",
            "scope": scope,
            "source": "homebrew",
            "owner": user.id,
        },
        type="class_features",
        scope=scope,
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-classes", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-classes/{class_slug}")
def update_custom_class(
    campaign_id: int,
    class_slug: str,
    name: str = Form(...),
    hit_die: str = Form("8"),
    prof_armor: str = Form(""),
    prof_weapons: str = Form(""),
    prof_tools: str = Form(""),
    prof_saving_throws: str = Form(""),
    prof_skills: str = Form(""),
    spellcasting_ability: str = Form(""),
    equipment: str = Form(""),
    features_json: str = Form(""),
    spell_list_json: str = Form(""),
    resources_json: str = Form(""),
    mc_prereq_str: str = Form(""),
    mc_prereq_dex: str = Form(""),
    mc_prereq_con: str = Form(""),
    mc_prereq_int: str = Form(""),
    mc_prereq_wis: str = Form(""),
    mc_prereq_cha: str = Form(""),
    mc_prereq_mode: str = Form("all"),
    multiclass_proficiencies: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Update everything but the slug. Sheets reference it; renames
    change the display name only. Delete + recreate to change the slug."""
    _require_gm_for_campaign(campaign_id, user, db)
    scope = f"campaign-{campaign_id}"
    existing = local_content.resolve(class_slug, type="class_features", campaign_id=campaign_id)
    if not existing or existing[1] != "local-homebrew":
        raise HTTPException(404, "Custom class not found")
    prev = existing[0]

    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    hd = _normalize_hit_die(hit_die)
    spc = _normalize_spellcasting_ability(spellcasting_ability)
    features = _parse_custom_subclass_features(features_json)
    spell_list = _parse_spell_list_json(spell_list_json)
    resources = _parse_class_resources_json(resources_json)
    mc_prereqs = _parse_multiclass_prereq_abilities({
        "str": mc_prereq_str, "dex": mc_prereq_dex, "con": mc_prereq_con,
        "int": mc_prereq_int, "wis": mc_prereq_wis, "cha": mc_prereq_cha,
    })
    mc_mode = _normalize_multiclass_mode(mc_prereq_mode)

    local_content.write_homebrew(
        {
            "slug": class_slug,
            "name": name_n,
            "hit_die": hd,
            "prof_armor": (prof_armor or "").strip()[:500],
            "prof_weapons": (prof_weapons or "").strip()[:500],
            "prof_tools": (prof_tools or "").strip()[:500],
            "prof_saving_throws": (prof_saving_throws or "").strip()[:120],
            "prof_skills": (prof_skills or "").strip()[:500],
            "spellcasting_ability": spc,
            "equipment": (equipment or "").strip()[:4000],
            "features": features,
            "spell_list": spell_list,
            "resources": resources,
            "multiclass_prereq_abilities": mc_prereqs,
            "multiclass_prereq_mode": mc_mode,
            "multiclass_proficiencies": (multiclass_proficiencies or "").strip()[:500],
            "actions": prev.get("actions") or [],
            "system": "dnd5e",
            "scope": scope,
            "source": "homebrew",
            "owner": prev.get("owner") or user.id,
        },
        type="class_features",
        scope=scope,
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-classes", status_code=303
    )


@router.get("/api/campaign/{campaign_id}/custom-class-resources")
def custom_class_resources(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Return every homebrew class resource recipe for this campaign.

    The sheet merges these into ``window._CLASS_RESOURCES`` at load time
    so the existing Class Resources panel surfaces homebrew counters
    alongside the curated SRD ones. Each record carries the ``class``
    slug it belongs to so the panel's existing filter-by-class logic
    works unchanged.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    # Any campaign member can read this (it's static homebrew data — the
    # GM authored it so the players could see it). Admins always allowed.
    if not user.is_admin and not _user_is_gm(user, campaign, db):
        is_member = db.query(CampaignMembership).filter(
            CampaignMembership.campaign_id == campaign_id,
            CampaignMembership.user_id == user.id,
        ).first()
        if not is_member:
            raise HTTPException(403, "Not a member of this campaign")

    records, _ = local_content.search(
        type="class_features", campaign_id=campaign_id, limit=500,
    )
    results: list[dict] = []
    for rec_file in records:
        if rec_file.get("_source") != "local-homebrew":
            continue
        cls_slug = rec_file.get("slug") or ""
        for rec in (rec_file.get("resources") or []):
            if not isinstance(rec, dict):
                continue
            results.append({**rec, "class": cls_slug, "subclass": None})
    return {"results": results}


@router.get("/api/character/{char_id}/multiclass-check")
def multiclass_check(
    char_id: int,
    target_class: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Check whether a character meets the multiclass prerequisites to add
    a level in ``target_class``.

    Resolution: campaign-scoped homebrew classes win over the shipped FS
    overrides, just like every other class lookup. If the target class has
    no prereq data, returns ``ok=true`` with an explanatory ``note`` —
    callers should treat that as "framework doesn't know the rules; trust
    the GM."
    """
    if not target_class:
        raise HTTPException(400, "target_class required")
    char = db.query(Character).filter(Character.id == char_id).first()
    if not char:
        raise HTTPException(404, "Character not found")

    # Auth: owner OR GM/admin of the campaign.
    campaign = None
    if char.campaign_id:
        campaign = db.query(Campaign).filter(Campaign.id == char.campaign_id).first()
    if not (char.owner_user_id == user.id
            or user.is_admin
            or (campaign and _user_is_gm(user, campaign, db))):
        raise HTTPException(403, "No access to this character")

    target_slug = target_class.strip().lower()
    scopes = [f"campaign:{char.campaign_id}", "global"] if char.campaign_id else ["global"]
    from .. import local_features
    record, _source = local_features.resolve_class(target_slug, scopes=scopes, db=db)

    if not record:
        return {
            "ok": True,
            "target_name": target_class,
            "reasons": [],
            "prereqs": {"abilities": {}, "mode": "all"},
            "proficiencies": "",
            "note": "No prerequisite data found for this class — no checks enforced.",
        }

    prereqs = record.get("multiclass_prereq_abilities") or {}
    mode = (record.get("multiclass_prereq_mode") or "all").lower()
    profs = record.get("multiclass_proficiencies") or ""
    target_name = record.get("name") or target_class

    if not prereqs:
        return {
            "ok": True,
            "target_name": target_name,
            "reasons": [],
            "prereqs": {"abilities": {}, "mode": mode},
            "proficiencies": profs,
            "note": f"{target_name} has no defined multiclass prerequisites.",
        }

    # Sheets store ability scores as uppercase 3-letter keys under
    # ``sheet.abilities`` (STR, DEX, …).  Fall through to lowercase and
    # default to 10 so partially-built sheets don't crash the check.
    abilities = (char.sheet or {}).get("abilities") or {}

    def _score(ab: str) -> int:
        v = abilities.get(ab.upper())
        if v is None:
            v = abilities.get(ab.lower())
        try:
            return int(v) if v is not None else 10
        except (TypeError, ValueError):
            return 10

    failed: list[str] = []
    passed: list[str] = []
    for ab, min_score in prereqs.items():
        cur = _score(ab)
        if cur < int(min_score):
            failed.append(f"{ab.upper()} {cur} (needs {min_score})")
        else:
            passed.append(f"{ab.upper()} {cur} >= {min_score}")

    if mode == "any":
        ok = bool(passed)
        if ok:
            reasons: list[str] = []
        else:
            reasons = [
                "At least one ability minimum must be met (mode: any). "
                "All failed: " + ", ".join(failed)
            ]
    else:  # "all"
        ok = not failed
        reasons = [f"Missing required minimum: {r}" for r in failed]

    return {
        "ok": ok,
        "target_name": target_name,
        "reasons": reasons,
        "prereqs": {"abilities": prereqs, "mode": mode},
        "proficiencies": profs,
    }


@router.post("/campaign/{campaign_id}/custom-classes/{class_slug}/delete")
def delete_custom_class(
    campaign_id: int,
    class_slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_gm_for_campaign(campaign_id, user, db)
    scope = f"campaign-{campaign_id}"
    ok = local_content.delete_homebrew(class_slug, type="class_features", scope=scope)
    if not ok:
        raise HTTPException(404, "Custom class not found")
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-classes", status_code=303
    )


# ── Custom races (GM-authored homebrew) ─────────────────────────────────────
#
# Mirror of the custom-class routes for races.  Shape closely matches the
# Open5e v1 race object so the existing ``format_race_text`` /
# ``parse_race_traits`` helpers in ``open5e_local.py`` can render homebrew
# without any code changes.

_VALID_SIZES = {"", "Tiny", "Small", "Medium", "Large", "Huge", "Gargantuan"}


def _normalize_race_size(raw: str) -> str:
    v = (raw or "").strip()
    if not v:
        return ""
    # Accept any-case input but persist the canonical capitalisation.
    canon = v.title()
    if canon not in _VALID_SIZES:
        raise HTTPException(400, f"Race size must be one of: {', '.join(s for s in sorted(_VALID_SIZES) if s)}")
    return canon


def _parse_ability_bonuses(values: dict) -> list:
    """Build the Open5e-shaped ``ability_bonuses`` list from six form fields.

    Returns a list of ``{"attribute": "Strength", "bonus": 2}`` records.
    Empty fields are dropped; zero is treated as "no bonus" rather than
    explicitly storing a +0.
    """
    canonical = {
        "str": "Strength", "dex": "Dexterity", "con": "Constitution",
        "int": "Intelligence", "wis": "Wisdom", "cha": "Charisma",
    }
    out: list = []
    for ab, raw in values.items():
        v = (raw or "").strip()
        if not v:
            continue
        try:
            n = int(v)
        except ValueError:
            raise HTTPException(400, f"Ability bonus for {ab.upper()} must be an integer (got {raw!r})")
        if n == 0:
            continue
        if n < -10 or n > 10:
            raise HTTPException(400, f"Ability bonus for {ab.upper()} out of range (-10 to 10)")
        out.append({"attribute": canonical.get(ab, ab.title()), "bonus": n})
    return out


@router.post("/campaign/{campaign_id}/custom-races")
def create_custom_race(
    campaign_id: int,
    name: str = Form(...),
    size: str = Form(""),
    speed: str = Form("30"),
    age: str = Form(""),
    alignment: str = Form(""),
    languages: str = Form(""),
    ab_str: str = Form(""),
    ab_dex: str = Form(""),
    ab_con: str = Form(""),
    ab_int: str = Form(""),
    ab_wis: str = Form(""),
    ab_cha: str = Form(""),
    traits_json: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_gm_for_campaign(campaign_id, user, db)
    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    race_slug = _slugify_for_subclass(name_n, max_len=60)
    if not race_slug:
        raise HTTPException(400, "Name does not yield a valid slug — use letters or numbers")
    size_n = _normalize_race_size(size)
    try:
        speed_n = int(speed or "30")
    except ValueError:
        raise HTTPException(400, "Speed must be an integer (feet per round)")
    if speed_n < 0 or speed_n > 200:
        raise HTTPException(400, "Speed out of range (0–200)")
    ab_bonuses = _parse_ability_bonuses({
        "str": ab_str, "dex": ab_dex, "con": ab_con,
        "int": ab_int, "wis": ab_wis, "cha": ab_cha,
    })
    # Traits share the features list shape — same parser, same rules.
    traits = _parse_custom_subclass_features(traits_json)

    existing = local_content.resolve(race_slug, type="races", campaign_id=campaign_id)
    if existing and existing[1] == "local-homebrew":
        raise HTTPException(400, f"A homebrew race with slug '{race_slug}' already exists in this campaign")
    try:
        local_content.write_homebrew(
            {
                "slug": race_slug,
                "name": name_n,
                "ability_bonuses": ab_bonuses,
                "size": size_n,
                "speed": speed_n,
                "age": (age or "").strip()[:1000],
                "alignment": (alignment or "").strip()[:1000],
                "languages": (languages or "").strip()[:1000],
                "traits": traits,
                "actions": [],
                "system": "dnd5e",
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
                "owner": user.id,
            },
            type="races",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-races", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-races/{race_slug}")
def update_custom_race(
    campaign_id: int,
    race_slug: str,
    name: str = Form(...),
    size: str = Form(""),
    speed: str = Form("30"),
    age: str = Form(""),
    alignment: str = Form(""),
    languages: str = Form(""),
    ab_str: str = Form(""),
    ab_dex: str = Form(""),
    ab_con: str = Form(""),
    ab_int: str = Form(""),
    ab_wis: str = Form(""),
    ab_cha: str = Form(""),
    traits_json: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based race update by slug. ``race_slug`` is immutable —
    the form only mutates the display name and other fields."""
    _require_gm_for_campaign(campaign_id, user, db)
    hit = local_content.resolve(race_slug, type="races", campaign_id=campaign_id)
    if not hit or hit[1] != "local-homebrew":
        raise HTTPException(404, "Custom race not found")
    existing = hit[0]

    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    size_n = _normalize_race_size(size)
    try:
        speed_n = int(speed or "30")
    except ValueError:
        raise HTTPException(400, "Speed must be an integer (feet per round)")
    if speed_n < 0 or speed_n > 200:
        raise HTTPException(400, "Speed out of range (0–200)")
    ab_bonuses = _parse_ability_bonuses({
        "str": ab_str, "dex": ab_dex, "con": ab_con,
        "int": ab_int, "wis": ab_wis, "cha": ab_cha,
    })
    traits = _parse_custom_subclass_features(traits_json)

    try:
        local_content.write_homebrew(
            {
                **existing,
                "slug": existing.get("slug") or race_slug,
                "name": name_n,
                "ability_bonuses": ab_bonuses,
                "size": size_n,
                "speed": speed_n,
                "age": (age or "").strip()[:1000],
                "alignment": (alignment or "").strip()[:1000],
                "languages": (languages or "").strip()[:1000],
                "traits": traits,
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
            },
            type="races",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-races", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-races/{race_slug}/delete")
def delete_custom_race(
    campaign_id: int,
    race_slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based race delete by slug."""
    _require_gm_for_campaign(campaign_id, user, db)
    try:
        removed = local_content.delete_homebrew(
            race_slug, type="races", scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not removed:
        raise HTTPException(404, "Custom race not found")
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-races", status_code=303
    )


# ── Custom monsters (GM-authored homebrew stat blocks) ──────────────────────
#
# Mirror of the other custom-content routes. The beast picker filters by
# ``type=beast`` for Wild Shape / Polymorph; other types (humanoid, fiend,
# undead, …) surface in the picker only when "Free pick" is checked.

_VALID_MONSTER_TYPES = {
    "aberration", "beast", "celestial", "construct", "dragon", "elemental",
    "fey", "fiend", "giant", "humanoid", "monstrosity", "ooze", "plant",
    "undead",
}


def _normalize_monster_type(raw: str) -> str:
    v = (raw or "").strip().lower()
    if not v:
        return "beast"
    if v not in _VALID_MONSTER_TYPES:
        raise HTTPException(
            400,
            f"Monster type must be one of: {', '.join(sorted(_VALID_MONSTER_TYPES))}",
        )
    return v


def _parse_monster_speed(form: dict) -> dict:
    """Six optional speed fields (walk/fly/swim/climb/burrow/hover-as-flag)
    → dict suitable for the Open5e shape. Drops zeros. Walk defaults to 30
    if every field is blank so the monster isn't accidentally rooted."""
    out: dict = {}
    for kind in ("walk", "fly", "swim", "climb", "burrow"):
        raw = (form.get(f"speed_{kind}") or "").strip()
        if not raw:
            continue
        try:
            n = int(raw)
        except ValueError:
            raise HTTPException(400, f"Speed.{kind} must be an integer (got {raw!r})")
        if n < 0 or n > 999:
            raise HTTPException(400, f"Speed.{kind} out of range (0–999)")
        if n > 0:
            out[kind] = n
    if not out:
        out["walk"] = 30
    return out


def _parse_cr(raw: str) -> str:
    """Accept "0", "1/8", "1/4", "1/2", or any integer 1–30. Stored as
    text to preserve fractional notation."""
    v = (raw or "0").strip()
    fractions = {"0", "1/8", "1/4", "1/2"}
    if v in fractions:
        return v
    try:
        n = int(v)
    except ValueError:
        raise HTTPException(400, "Challenge rating must be 0, 1/8, 1/4, 1/2, or an integer 1–30")
    if n < 0 or n > 30:
        raise HTTPException(400, "Challenge rating out of range (0–30)")
    return str(n)


def _parse_ability_score(label: str, raw: str) -> int:
    try:
        n = int(raw or "10")
    except ValueError:
        raise HTTPException(400, f"{label} must be an integer (got {raw!r})")
    if n < 1 or n > 40:
        raise HTTPException(400, f"{label} out of range (1–40)")
    return n


def _coalesce_monster_actions(actions_json: str, reactions_json: str,
                              special_abilities_json: str, legendary_actions_json: str) -> list[dict]:
    """v2.0.0 helper: take the 4 legacy action-list JSON form fields and
    fold them into the single ``actions: list[Action]`` array shape that
    the Monster Pydantic model uses, with a ``category`` discriminator on
    each entry. Mirrors the migration helper in app/_migrate_v52.py.

    v2.3.8: preserves the structured attack fields (``attack_roll``,
    ``attack_bonus``, ``damage``, ``damage_type``, ``save_ability``,
    ``save_dc``) that the action-mode editor now emits on the Actions
    fieldset, so the homebrew monster's stat-block view can render
    Attack / Save / Damage buttons via ``renderActionButtons``. Passed
    through via the shared parser's ``extra_keys`` parameter."""
    import re as _re
    _attack_keys = (
        "attack_roll", "attack_bonus", "damage", "damage_type",
        "save_ability", "save_dc",
    )
    out: list[dict] = []
    for raw, cat in (
        (actions_json,            "action"),
        (reactions_json,          "reaction"),
        (special_abilities_json,  "special_ability"),
        (legendary_actions_json,  "legendary_action"),
    ):
        for entry in _parse_custom_subclass_features(raw, extra_keys=_attack_keys):
            if not isinstance(entry, dict):
                continue
            name = (entry.get("name") or "").strip()
            slug_id = _re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or f"unnamed-{cat}"
            rec: dict = {
                "id": entry.get("id") or slug_id,
                "name": name,
                "desc": entry.get("desc") or "",
                "min_level": entry.get("level") or 1,
                "category": cat,
            }
            # Accept the attack keys on any category for forward-compatibility
            # (e.g. a Legendary action that itself involves an attack roll).
            for k in _attack_keys:
                v = entry.get(k)
                if v not in (None, "", False, 0):
                    rec[k] = v
            out.append(rec)
    return out


@router.post("/campaign/{campaign_id}/custom-monsters")
def create_custom_monster(
    campaign_id: int,
    name: str = Form(...),
    size: str = Form("Medium"),
    type: str = Form("beast"),
    alignment: str = Form("unaligned"),
    armor_class: str = Form("10"),
    armor_desc: str = Form(""),
    hit_points: str = Form("1"),
    hit_dice: str = Form(""),
    speed_walk: str = Form(""),
    speed_fly: str = Form(""),
    speed_swim: str = Form(""),
    speed_climb: str = Form(""),
    speed_burrow: str = Form(""),
    strength: str = Form("10"),
    dexterity: str = Form("10"),
    constitution: str = Form("10"),
    intelligence: str = Form("10"),
    wisdom: str = Form("10"),
    charisma: str = Form("10"),
    damage_vulnerabilities: str = Form(""),
    damage_resistances: str = Form(""),
    damage_immunities: str = Form(""),
    condition_immunities: str = Form(""),
    senses: str = Form(""),
    languages: str = Form(""),
    challenge_rating: str = Form("0"),
    actions_json: str = Form(""),
    reactions_json: str = Form(""),
    special_abilities_json: str = Form(""),
    legendary_actions_json: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_gm_for_campaign(campaign_id, user, db)
    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    monster_slug = _slugify_for_subclass(name_n, max_len=80)
    if not monster_slug:
        raise HTTPException(400, "Name does not yield a valid slug — use letters or numbers")
    size_n = _normalize_race_size(size) or "Medium"  # reuse the size validator
    type_n = _normalize_monster_type(type)
    try:
        ac = int(armor_class or "10")
    except ValueError:
        raise HTTPException(400, "Armor class must be an integer")
    if ac < 1 or ac > 40:
        raise HTTPException(400, "Armor class out of range (1–40)")
    try:
        hp = int(hit_points or "1")
    except ValueError:
        raise HTTPException(400, "Hit points must be an integer")
    if hp < 1 or hp > 9999:
        raise HTTPException(400, "Hit points out of range (1–9999)")
    speed = _parse_monster_speed({
        "speed_walk": speed_walk, "speed_fly": speed_fly, "speed_swim": speed_swim,
        "speed_climb": speed_climb, "speed_burrow": speed_burrow,
    })
    cr = _parse_cr(challenge_rating)

    existing_hit = local_content.resolve(monster_slug, type="monsters", campaign_id=campaign_id)
    if existing_hit and existing_hit[1] == "local-homebrew":
        raise HTTPException(400, f"A homebrew monster with slug '{monster_slug}' already exists in this campaign")
    try:
        local_content.write_homebrew(
            {
                "slug": monster_slug,
                "name": name_n,
                "size": size_n,
                "type": type_n,
                "alignment": (alignment or "").strip()[:120],
                "armor_class": ac,
                "armor_desc": (armor_desc or "").strip()[:120],
                "hit_points": hp,
                "hit_dice": (hit_dice or "").strip()[:40],
                "speed": speed,
                "strength": _parse_ability_score("STR", strength),
                "dexterity": _parse_ability_score("DEX", dexterity),
                "constitution": _parse_ability_score("CON", constitution),
                "intelligence": _parse_ability_score("INT", intelligence),
                "wisdom": _parse_ability_score("WIS", wisdom),
                "charisma": _parse_ability_score("CHA", charisma),
                "damage_vulnerabilities": (damage_vulnerabilities or "").strip()[:500],
                "damage_resistances": (damage_resistances or "").strip()[:500],
                "damage_immunities": (damage_immunities or "").strip()[:500],
                "condition_immunities": (condition_immunities or "").strip()[:500],
                "senses": (senses or "").strip()[:500],
                "languages": (languages or "").strip()[:500],
                "challenge_rating": cr,
                # v2.0.0 unified action list with category discriminator.
                "actions": _coalesce_monster_actions(
                    actions_json, reactions_json, special_abilities_json, legendary_actions_json,
                ),
                "system": "dnd5e",
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
                "owner": user.id,
            },
            type="monsters",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-monsters", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-monsters/{monster_slug}")
def update_custom_monster(
    campaign_id: int,
    monster_slug: str,
    name: str = Form(...),
    size: str = Form("Medium"),
    type: str = Form("beast"),
    alignment: str = Form("unaligned"),
    armor_class: str = Form("10"),
    armor_desc: str = Form(""),
    hit_points: str = Form("1"),
    hit_dice: str = Form(""),
    speed_walk: str = Form(""),
    speed_fly: str = Form(""),
    speed_swim: str = Form(""),
    speed_climb: str = Form(""),
    speed_burrow: str = Form(""),
    strength: str = Form("10"),
    dexterity: str = Form("10"),
    constitution: str = Form("10"),
    intelligence: str = Form("10"),
    wisdom: str = Form("10"),
    charisma: str = Form("10"),
    damage_vulnerabilities: str = Form(""),
    damage_resistances: str = Form(""),
    damage_immunities: str = Form(""),
    condition_immunities: str = Form(""),
    senses: str = Form(""),
    languages: str = Form(""),
    challenge_rating: str = Form("0"),
    actions_json: str = Form(""),
    reactions_json: str = Form(""),
    special_abilities_json: str = Form(""),
    legendary_actions_json: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based monster update by slug. ``monster_slug`` is immutable —
    token templates and beast-favorites reference it."""
    _require_gm_for_campaign(campaign_id, user, db)
    hit = local_content.resolve(monster_slug, type="monsters", campaign_id=campaign_id)
    if not hit or hit[1] != "local-homebrew":
        raise HTTPException(404, "Custom monster not found")
    existing = hit[0]

    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    size_n = _normalize_race_size(size) or "Medium"
    type_n = _normalize_monster_type(type)
    try:
        ac = int(armor_class or "10")
    except ValueError:
        raise HTTPException(400, "Armor class must be an integer")
    if ac < 1 or ac > 40:
        raise HTTPException(400, "Armor class out of range (1–40)")
    try:
        hp = int(hit_points or "1")
    except ValueError:
        raise HTTPException(400, "Hit points must be an integer")
    if hp < 1 or hp > 9999:
        raise HTTPException(400, "Hit points out of range (1–9999)")
    speed = _parse_monster_speed({
        "speed_walk": speed_walk, "speed_fly": speed_fly, "speed_swim": speed_swim,
        "speed_climb": speed_climb, "speed_burrow": speed_burrow,
    })
    cr = _parse_cr(challenge_rating)

    try:
        local_content.write_homebrew(
            {
                **existing,
                "slug": existing.get("slug") or monster_slug,
                "name": name_n,
                "size": size_n,
                "type": type_n,
                "alignment": (alignment or "").strip()[:120],
                "armor_class": ac,
                "armor_desc": (armor_desc or "").strip()[:120],
                "hit_points": hp,
                "hit_dice": (hit_dice or "").strip()[:40],
                "speed": speed,
                "strength": _parse_ability_score("STR", strength),
                "dexterity": _parse_ability_score("DEX", dexterity),
                "constitution": _parse_ability_score("CON", constitution),
                "intelligence": _parse_ability_score("INT", intelligence),
                "wisdom": _parse_ability_score("WIS", wisdom),
                "charisma": _parse_ability_score("CHA", charisma),
                "damage_vulnerabilities": (damage_vulnerabilities or "").strip()[:500],
                "damage_resistances": (damage_resistances or "").strip()[:500],
                "damage_immunities": (damage_immunities or "").strip()[:500],
                "condition_immunities": (condition_immunities or "").strip()[:500],
                "senses": (senses or "").strip()[:500],
                "languages": (languages or "").strip()[:500],
                "challenge_rating": cr,
                "actions": _coalesce_monster_actions(
                    actions_json, reactions_json, special_abilities_json, legendary_actions_json,
                ),
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
            },
            type="monsters",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-monsters", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-monsters/{monster_slug}/delete")
def delete_custom_monster(
    campaign_id: int,
    monster_slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based monster delete by slug."""
    _require_gm_for_campaign(campaign_id, user, db)
    try:
        removed = local_content.delete_homebrew(
            monster_slug, type="monsters", scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not removed:
        raise HTTPException(404, "Custom monster not found")
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-monsters", status_code=303
    )


# ── Custom backgrounds (GM-authored homebrew) ───────────────────────────────

@router.post("/campaign/{campaign_id}/custom-backgrounds")
def create_custom_background(
    campaign_id: int,
    name: str = Form(...),
    description: str = Form(""),
    skill_proficiencies: str = Form(""),
    tool_proficiencies: str = Form(""),
    languages: str = Form(""),
    equipment: str = Form(""),
    feature_name: str = Form(""),
    feature_desc: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based homebrew create. See create_custom_feat for the pattern."""
    _require_gm_for_campaign(campaign_id, user, db)
    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    slug = _slugify_for_subclass(name_n, max_len=60)
    if not slug:
        raise HTTPException(400, "Name does not yield a valid slug — use letters or numbers")
    existing = local_content.resolve(slug, type="backgrounds", campaign_id=campaign_id)
    if existing and existing[1] == "local-homebrew":
        raise HTTPException(400, f"A homebrew background with slug '{slug}' already exists in this campaign")
    try:
        local_content.write_homebrew(
            {
                "slug": slug,
                "name": name_n,
                "description": (description or "").strip()[:8000],
                "skill_proficiencies": (skill_proficiencies or "").strip()[:500],
                "tool_proficiencies": (tool_proficiencies or "").strip()[:500],
                "languages": (languages or "").strip()[:500],
                "equipment": (equipment or "").strip()[:4000],
                "feature_name": (feature_name or "").strip()[:160],
                "feature_desc": (feature_desc or "").strip()[:4000],
                "actions": [],
                "system": "dnd5e",
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
                "owner": user.id,
            },
            type="backgrounds",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-backgrounds", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-backgrounds/{bg_slug}")
def update_custom_background(
    campaign_id: int,
    bg_slug: str,
    name: str = Form(...),
    description: str = Form(""),
    skill_proficiencies: str = Form(""),
    tool_proficiencies: str = Form(""),
    languages: str = Form(""),
    equipment: str = Form(""),
    feature_name: str = Form(""),
    feature_desc: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based homebrew update by slug."""
    _require_gm_for_campaign(campaign_id, user, db)
    hit = local_content.resolve(bg_slug, type="backgrounds", campaign_id=campaign_id)
    if not hit or hit[1] != "local-homebrew":
        raise HTTPException(404, "Custom background not found")
    existing = hit[0]
    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    try:
        local_content.write_homebrew(
            {
                **existing,
                "slug": existing.get("slug") or bg_slug,
                "name": name_n,
                "description": (description or "").strip()[:8000],
                "skill_proficiencies": (skill_proficiencies or "").strip()[:500],
                "tool_proficiencies": (tool_proficiencies or "").strip()[:500],
                "languages": (languages or "").strip()[:500],
                "equipment": (equipment or "").strip()[:4000],
                "feature_name": (feature_name or "").strip()[:160],
                "feature_desc": (feature_desc or "").strip()[:4000],
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
            },
            type="backgrounds",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-backgrounds", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-backgrounds/{bg_slug}/delete")
def delete_custom_background(
    campaign_id: int,
    bg_slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based homebrew delete by slug."""
    _require_gm_for_campaign(campaign_id, user, db)
    try:
        removed = local_content.delete_homebrew(
            bg_slug, type="backgrounds", scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not removed:
        raise HTTPException(404, "Custom background not found")
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-backgrounds", status_code=303
    )


# ── Custom feats (GM-authored homebrew) ─────────────────────────────────────

@router.post("/campaign/{campaign_id}/custom-feats")
def create_custom_feat(
    campaign_id: int,
    name: str = Form(...),
    prerequisite: str = Form(""),
    desc: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Create a campaign-scoped homebrew feat as a JSON file in the homebrew
    Docker volume. The slug is derived from the name and must be unique
    within the campaign-scope directory. v2.0.0: replaces the legacy
    CustomFeat DB write path."""
    _require_gm_for_campaign(campaign_id, user, db)
    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    slug = _slugify_for_subclass(name_n, max_len=80)
    if not slug:
        raise HTTPException(400, "Name does not yield a valid slug — use letters or numbers")
    # Uniqueness check against the file-based homebrew. Note: resolve() walks
    # campaign-scope first, then global — we only care about a clash inside
    # this campaign's scope so the broader-tier records don't false-positive.
    existing = local_content.resolve(slug, type="feats", campaign_id=campaign_id)
    if existing and (existing[1] == "local-homebrew"):
        raise HTTPException(400, f"A homebrew feat with slug '{slug}' already exists in this campaign")
    try:
        local_content.write_homebrew(
            {
                "slug": slug,
                "name": name_n,
                "prerequisite": (prerequisite or "").strip()[:500],
                "desc": (desc or "").strip()[:8000],
                "actions": [],
                "system": "dnd5e",
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
                "owner": user.id,
            },
            type="feats",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-feats", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-feats/{feat_slug}")
def update_custom_feat(
    campaign_id: int,
    feat_slug: str,
    name: str = Form(...),
    prerequisite: str = Form(""),
    desc: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Update a campaign-scoped homebrew feat by slug. v2.0.0: feat_slug
    replaces the legacy int feat_id in the URL contract — the file-based
    backing has no integer primary key."""
    _require_gm_for_campaign(campaign_id, user, db)
    hit = local_content.resolve(feat_slug, type="feats", campaign_id=campaign_id)
    if not hit or hit[1] != "local-homebrew":
        raise HTTPException(404, "Custom feat not found")
    existing = hit[0]
    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    # Atomic rewrite: preserve actions, owner, attribution; replace editable
    # fields with the form payload.
    try:
        local_content.write_homebrew(
            {
                **existing,
                "slug": existing.get("slug") or feat_slug,
                "name": name_n,
                "prerequisite": (prerequisite or "").strip()[:500],
                "desc": (desc or "").strip()[:8000],
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
            },
            type="feats",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-feats", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-feats/{feat_slug}/delete")
def delete_custom_feat(
    campaign_id: int,
    feat_slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Delete a campaign-scoped homebrew feat by slug. v2.0.0: feat_slug
    replaces the legacy int feat_id in the URL contract."""
    _require_gm_for_campaign(campaign_id, user, db)
    try:
        removed = local_content.delete_homebrew(
            feat_slug, type="feats", scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not removed:
        raise HTTPException(404, "Custom feat not found")
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-feats", status_code=303
    )


# ── Homebrew clone (v2.3.37) ────────────────────────────────────────────────
# One generic helper + six thin route handlers. Each handler accepts the
# type-specific URL contract (``feat_slug`` / ``bg_slug`` / ``monster_slug``
# / ``race_slug`` / ``class_slug`` / ``combined_slug`` for subclasses) and
# delegates the actual clone work to ``_clone_homebrew_record`` which
# handles the source lookup, slug-collision-safe new slug generation, name
# rewrite (``"Copy of <original>"``), and disk write. Each redirects back
# to ``/campaign/{cid}/settings#custom-{type}`` so the GM sees the newly-
# cloned entry in the homebrew list and can expand its editor inline. No
# clone for shipped SRD content — only ``local-homebrew`` source records
# can be cloned (the resolver source check guards against accidentally
# forking SRD into homebrew).


def _unique_clone_slug(base: str, content_type: str, campaign_id: int) -> str:
    """Build a fresh, collision-safe homebrew slug for a clone.

    Starts with ``copy-of-{base}`` (after re-slugifying — handles base slugs
    that themselves came from "Copy of Copy of …" deep clones). If that
    collides with an existing homebrew record in the campaign scope, appends
    ``-2``, ``-3``, … until the resolver returns no hit. Bounded loop —
    we'll never realistically iterate past a few attempts, but cap at 50
    to be safe.
    """
    base = _slugify_for_subclass(base, max_len=60) or "clone"
    candidate = _slugify_for_subclass(f"copy-of-{base}", max_len=80) or "copy"
    suffix = 1
    while suffix < 50:
        hit = local_content.resolve(
            candidate, type=content_type, campaign_id=campaign_id,
        )
        if not hit:
            return candidate
        suffix += 1
        candidate = _slugify_for_subclass(f"copy-of-{base}-{suffix}", max_len=80)
    raise HTTPException(500, "Could not generate a unique clone slug")


def _clone_homebrew_record(
    *,
    campaign_id: int,
    user: User,
    db: Session,
    src_slug: str,
    content_type: str,
    target_slug: Optional[str] = None,
) -> str:
    """Read a homebrew source record, write a clone with a fresh slug + a
    'Copy of …' name. Returns the new slug. Raises 404 if the source
    isn't a campaign-scope homebrew (won't clone shipped SRD content)
    and 403 if the caller isn't the GM.

    ``target_slug`` lets the subclass clone path supply a fully-qualified
    ``{class_slug}-{subclass_slug}`` instead of letting the helper pick
    a flat ``copy-of-{slug}`` — subclass slugs MUST stay namespaced by
    their parent class so the resolver can route lookups correctly.
    """
    _require_gm_for_campaign(campaign_id, user, db)
    hit = local_content.resolve(src_slug, type=content_type, campaign_id=campaign_id)
    if not hit or hit[1] != "local-homebrew":
        raise HTTPException(404, "Source homebrew record not found")
    source, _ = hit
    new_slug = target_slug or _unique_clone_slug(
        src_slug, content_type, campaign_id,
    )
    new_name = f"Copy of {source.get('name') or src_slug}"
    new_record = {
        **source,
        "slug": new_slug,
        "name": new_name[:200],
        "scope": f"campaign-{campaign_id}",
        "source": "homebrew",
    }
    try:
        local_content.write_homebrew(
            new_record, type=content_type, scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return new_slug


@router.post("/campaign/{campaign_id}/custom-feats/{feat_slug}/clone")
def clone_custom_feat(
    campaign_id: int, feat_slug: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    _clone_homebrew_record(
        campaign_id=campaign_id, user=user, db=db,
        src_slug=feat_slug, content_type="feats",
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-feats", status_code=303,
    )


@router.post("/campaign/{campaign_id}/custom-backgrounds/{bg_slug}/clone")
def clone_custom_background(
    campaign_id: int, bg_slug: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    _clone_homebrew_record(
        campaign_id=campaign_id, user=user, db=db,
        src_slug=bg_slug, content_type="backgrounds",
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-backgrounds", status_code=303,
    )


@router.post("/campaign/{campaign_id}/custom-races/{race_slug}/clone")
def clone_custom_race(
    campaign_id: int, race_slug: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    _clone_homebrew_record(
        campaign_id=campaign_id, user=user, db=db,
        src_slug=race_slug, content_type="races",
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-races", status_code=303,
    )


@router.post("/campaign/{campaign_id}/custom-monsters/{monster_slug}/clone")
def clone_custom_monster(
    campaign_id: int, monster_slug: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    _clone_homebrew_record(
        campaign_id=campaign_id, user=user, db=db,
        src_slug=monster_slug, content_type="monsters",
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-monsters", status_code=303,
    )


@router.post("/campaign/{campaign_id}/custom-classes/{class_slug}/clone")
def clone_custom_class(
    campaign_id: int, class_slug: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    _clone_homebrew_record(
        campaign_id=campaign_id, user=user, db=db,
        src_slug=class_slug, content_type="class_features",
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-classes", status_code=303,
    )


@router.post("/campaign/{campaign_id}/custom-subclasses/{combined_slug}/clone")
def clone_custom_subclass(
    campaign_id: int, combined_slug: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    """Subclass slugs are ``{class_slug}-{subclass_slug}`` to keep them
    namespaced by parent class. Preserve the class prefix; only mutate
    the subclass part so the clone stays a sibling of its parent class.
    Falls back to letting ``_unique_clone_slug`` pick a flat name when
    the source slug doesn't contain a recognizable class prefix."""
    _require_gm_for_campaign(campaign_id, user, db)
    hit = local_content.resolve(
        combined_slug, type="subclass_features", campaign_id=campaign_id,
    )
    if not hit or hit[1] != "local-homebrew":
        raise HTTPException(404, "Source homebrew subclass not found")
    source, _ = hit
    cls_slug = (source.get("class_slug") or "").strip()
    sub_slug = (source.get("slug") or combined_slug).strip()
    # Strip the class prefix from the combined slug to extract just the
    # subclass portion, then re-prefix with ``copy-of-`` so the result
    # stays under the same parent class. ``copy-of-...`` instead of
    # ``...-copy`` matches the flat clones' convention.
    if cls_slug and sub_slug.startswith(cls_slug + "-"):
        bare_sub = sub_slug[len(cls_slug) + 1:]
    else:
        bare_sub = sub_slug
    target_slug = None
    if cls_slug and bare_sub:
        candidate = _slugify_for_subclass(
            f"{cls_slug}-copy-of-{bare_sub}", max_len=80,
        )
        # Collision check — append numeric suffix if needed.
        suffix = 1
        while suffix < 50:
            hit = local_content.resolve(
                candidate, type="subclass_features", campaign_id=campaign_id,
            )
            if not hit:
                target_slug = candidate
                break
            suffix += 1
            candidate = _slugify_for_subclass(
                f"{cls_slug}-copy-of-{bare_sub}-{suffix}", max_len=80,
            )
    _clone_homebrew_record(
        campaign_id=campaign_id, user=user, db=db,
        src_slug=combined_slug, content_type="subclass_features",
        target_slug=target_slug,
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-subclasses", status_code=303,
    )


# ── Homebrew import / export / template ─────────────────────────────────────
#
# Bulk JSON I/O for every homebrew content type in one combined file. The
# file format is intentionally a near-mirror of the DB column names per row
# so a hand-edited template (downloaded from ``/homebrew/template``) goes
# straight back in without any client-side massaging. Import deduplicates
# on slug — existing rows in the destination campaign are skipped rather
# than overwritten, matching the safer default of "import only adds".

HOMEBREW_EXPORT_VERSION = 1


# _class_to_dict / _subclass_to_dict / _race_to_dict helpers removed in
# v2.0.0 — export endpoint inlines projections from local_content results.


def _monster_record_to_export(r: dict) -> dict:
    """Helper: project a file-based monster record back to the legacy export
    shape (with `monster_slug` + 4 split action lists). v2.0.0."""
    by_cat: dict[str, list] = {"action": [], "reaction": [], "special_ability": [], "legendary_action": []}
    for a in r.get("actions") or []:
        cat = a.get("category") or "action"
        if cat in by_cat:
            by_cat[cat].append({"name": a.get("name"), "desc": a.get("desc"), "level": a.get("min_level")})
    return {
        "monster_slug": r.get("slug"),
        "name": r.get("name"),
        "size": r.get("size") or "Medium",
        "type": r.get("type") or "beast",
        "alignment": r.get("alignment") or "unaligned",
        "armor_class": r.get("armor_class"),
        "armor_desc": r.get("armor_desc") or "",
        "hit_points": r.get("hit_points"),
        "hit_dice": r.get("hit_dice") or "",
        "speed": r.get("speed") or {"walk": 30},
        "strength": r.get("strength"), "dexterity": r.get("dexterity"),
        "constitution": r.get("constitution"), "intelligence": r.get("intelligence"),
        "wisdom": r.get("wisdom"), "charisma": r.get("charisma"),
        "damage_vulnerabilities": r.get("damage_vulnerabilities") or "",
        "damage_resistances": r.get("damage_resistances") or "",
        "damage_immunities": r.get("damage_immunities") or "",
        "condition_immunities": r.get("condition_immunities") or "",
        "senses": r.get("senses") or "",
        "languages": r.get("languages") or "",
        "challenge_rating": r.get("challenge_rating") or "0",
        "actions": by_cat["action"],
        "reactions": by_cat["reaction"],
        "special_abilities": by_cat["special_ability"],
        "legendary_actions": by_cat["legendary_action"],
    }


# _background_to_dict helper removed in v2.0.0 — export endpoint inlines
# the legacy-field-name projection from local_content.search results.


# _feat_to_dict helper removed in v2.0.0 — the export endpoint now reads
# directly from local_content.search() and projects to the legacy field-name
# shape inline. Other Custom* types still have their helpers until their own
# Phase C step lands.


@router.get("/api/campaign/{campaign_id}/homebrew/export")
def export_homebrew(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Return every homebrew row for this campaign in one combined JSON
    pack. GM only. The shape matches what /homebrew/import accepts so
    round-tripping export → import into another campaign works without
    edits."""
    campaign = _require_gm_for_campaign(campaign_id, user, db)
    from datetime import datetime as _dt
    return {
        "format": "simplevtt-homebrew",
        "version": HOMEBREW_EXPORT_VERSION,
        "campaign": campaign.name,
        "exported_at": _dt.utcnow().isoformat() + "Z",
        # Classes: v2.0.0 — file-based homebrew tier, project to legacy `class_slug`.
        "classes": [
            {
                "class_slug": r.get("slug"),
                "name": r.get("name"),
                "hit_die": r.get("hit_die") or 8,
                "prof_armor": r.get("prof_armor") or "",
                "prof_weapons": r.get("prof_weapons") or "",
                "prof_tools": r.get("prof_tools") or "",
                "prof_saving_throws": r.get("prof_saving_throws") or "",
                "prof_skills": r.get("prof_skills") or "",
                "spellcasting_ability": r.get("spellcasting_ability") or "",
                "equipment": r.get("equipment") or "",
                "features": r.get("features") or [],
                "spell_list": r.get("spell_list") or [],
                "multiclass_prereq_abilities": r.get("multiclass_prereq_abilities") or {},
                "multiclass_prereq_mode": r.get("multiclass_prereq_mode") or "all",
                "multiclass_proficiencies": r.get("multiclass_proficiencies") or "",
                "resources": r.get("resources") or [],
            }
            for r in local_content.search(type="class_features", campaign_id=campaign_id, limit=500)[0]
            if r.get("_source") == "local-homebrew"
        ],
        # Subclasses: v2.0.0 — file-based homebrew tier, project from combined
        # `<class>__<sub>` slug back to split fields the importer accepts.
        "subclasses": [
            {
                "class_slug": (r.get("slug") or "").partition("__")[0] or r.get("class_slug") or "",
                "sub_slug": (r.get("slug") or "").partition("__")[2] or r.get("slug") or "",
                "name": r.get("name"),
                "flavor": r.get("subclass_flavor") or r.get("flavor") or "",
                "features": r.get("features") or [],
            }
            for r in local_content.search(type="subclass_features", campaign_id=campaign_id, limit=500)[0]
            if r.get("_source") == "local-homebrew"
        ],
        # Races: v2.0.0 — file-based homebrew tier, project to legacy `race_slug`.
        "races": [
            {
                "race_slug": r.get("slug"),
                "name": r.get("name"),
                "ability_bonuses": r.get("ability_bonuses") or [],
                "size": r.get("size") or "",
                "speed": r.get("speed"),
                "age": r.get("age") or "",
                "alignment": r.get("alignment") or "",
                "languages": r.get("languages") or "",
                "traits": r.get("traits") or [],
            }
            for r in local_content.search(type="races", campaign_id=campaign_id, limit=500)[0]
            if r.get("_source") == "local-homebrew"
        ],
        "monsters": [
            _monster_record_to_export(r)
            for r in local_content.search(type="monsters", campaign_id=campaign_id, limit=500)[0]
            if r.get("_source") == "local-homebrew"
        ],
        # Backgrounds: v2.0.0 — file-based homebrew tier, projected back to
        # the legacy `background_slug` field for round-tripping.
        "backgrounds": [
            {
                "background_slug": r.get("slug"),
                "name": r.get("name"),
                "description": r.get("description") or "",
                "skill_proficiencies": r.get("skill_proficiencies") or "",
                "tool_proficiencies": r.get("tool_proficiencies") or "",
                "languages": r.get("languages") or "",
                "equipment": r.get("equipment") or "",
                "feature_name": r.get("feature_name") or "",
                "feature_desc": r.get("feature_desc") or "",
            }
            for r in local_content.search(type="backgrounds", campaign_id=campaign_id, limit=500)[0]
            if r.get("_source") == "local-homebrew"
        ],
        # Feats: v2.0.0 — read from file-based homebrew tier and project back
        # to the legacy `feat_slug` field name so existing exports round-trip
        # cleanly when re-imported (the importer accepts either `feat_slug`
        # or the new `slug` field).
        "feats": [
            {
                "feat_slug": r.get("slug"),
                "name": r.get("name"),
                "prerequisite": r.get("prerequisite") or "",
                "desc": r.get("desc") or "",
            }
            for r in local_content.search(type="feats", campaign_id=campaign_id, limit=500)[0]
            if r.get("_source") == "local-homebrew"
        ],
    }


@router.get("/api/campaign/{campaign_id}/homebrew/template")
def homebrew_template(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Return an annotated JSON template with one example row per content
    type. Slugs use the ``example-…`` prefix so a hand-edited template
    that's accidentally imported as-is is easy to spot and clean up."""
    _require_gm_for_campaign(campaign_id, user, db)
    return {
        "format": "simplevtt-homebrew",
        "version": HOMEBREW_EXPORT_VERSION,
        "_doc": [
            "One example row per content type. Fill in or delete each list as needed.",
            "Slugs are auto-generated from name on import — the slug field is informational.",
            "Import skips any row whose slug already exists in the destination campaign.",
        ],
        "classes": [{
            "class_slug": "example-class",
            "name": "Example Class",
            "hit_die": 8,
            "prof_armor": "Light armor",
            "prof_weapons": "Simple weapons",
            "prof_tools": "",
            "prof_saving_throws": "Dexterity, Intelligence",
            "prof_skills": "Choose two from Arcana, Investigation, Perception",
            "spellcasting_ability": "int",
            "equipment": "Starting equipment here",
            "features": [{"name": "Example Feature", "level": 1, "desc": "What it does."}],
            "spell_list": ["fire-bolt", "mage-hand"],
            "multiclass_prereq_abilities": {"int": 13},
            "multiclass_prereq_mode": "all",
            "multiclass_proficiencies": "Light armor",
            "resources": [{
                "key": "example-resource", "name": "Example Resource", "min_level": 2,
                "max_kind": "level_table", "max_table": {"2": 1, "10": 2},
                "reset": "short", "desc": "Refills on a short rest."
            }],
        }],
        "subclasses": [{
            "class_slug": "druid", "sub_slug": "example-circle",
            "name": "Example Circle",
            "flavor": "Druids of the example circle...",
            "features": [{"name": "Bonus Cantrip", "level": 2, "desc": "You learn one extra druid cantrip."}],
        }],
        "races": [{
            "race_slug": "example-race", "name": "Example Race",
            "ability_bonuses": [{"attribute": "Dexterity", "bonus": 2}, {"attribute": "Intelligence", "bonus": 1}],
            "size": "Medium", "speed": 30,
            "age": "Mature like humans; live 200 years.",
            "alignment": "Most are neutral.",
            "languages": "Common, one of your choice.",
            "traits": [{"name": "Darkvision", "desc": "You see in dim light within 60 feet."}],
        }],
        "monsters": [{
            "monster_slug": "example-monster", "name": "Example Monster",
            "size": "Medium", "type": "beast", "alignment": "unaligned",
            "armor_class": 13, "armor_desc": "natural armor",
            "hit_points": 22, "hit_dice": "4d8+4",
            "speed": {"walk": 40},
            "strength": 15, "dexterity": 14, "constitution": 13,
            "intelligence": 3, "wisdom": 12, "charisma": 6,
            "damage_resistances": "", "damage_immunities": "",
            "damage_vulnerabilities": "", "condition_immunities": "",
            "senses": "darkvision 60 ft., passive Perception 12",
            "languages": "",
            "challenge_rating": "1",
            "actions": [{"name": "Bite", "desc": "Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 7 (1d8 + 2) piercing damage."}],
            "reactions": [], "special_abilities": [], "legendary_actions": [],
        }],
        "backgrounds": [{
            "background_slug": "example-background", "name": "Example Background",
            "description": "Short narrative description.",
            "skill_proficiencies": "Survival, History",
            "tool_proficiencies": "Cartographer's tools",
            "languages": "One of your choice",
            "equipment": "A traveler's pack and 10 gp",
            "feature_name": "Signature Feature",
            "feature_desc": "What this background's signature feature does.",
        }],
        "feats": [{
            "feat_slug": "example-feat", "name": "Example Feat",
            "prerequisite": "Strength 13 or higher",
            "desc": "What the feat does.\n\n• Bullet one.\n• Bullet two.",
        }],
    }


def _safe_int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _safe_str(v, max_len: int = 500) -> str:
    s = str(v or "").strip()
    return s[:max_len]


@router.post("/api/campaign/{campaign_id}/homebrew/import")
async def import_homebrew(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Bulk-import homebrew rows from a JSON pack (matching the
    ``/homebrew/export`` shape).

    Rows whose slug already exists in this campaign are silently skipped
    so re-importing a pack you've already pulled in is a no-op. Each
    content type is processed independently — a malformed entry in one
    list doesn't kill the rest of the import. Returns per-type counts of
    ``created`` / ``skipped`` / ``errors`` so the GM can see what landed.
    """
    _require_gm_for_campaign(campaign_id, user, db)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Expected a JSON object — the export format root.")
    if body.get("format") and body["format"] != "simplevtt-homebrew":
        raise HTTPException(400, "Wrong format — expected ``simplevtt-homebrew``.")
    if body.get("version") and int(body.get("version", 0)) > HOMEBREW_EXPORT_VERSION:
        raise HTTPException(400, f"Pack version {body.get('version')} is newer than this server supports ({HOMEBREW_EXPORT_VERSION}). Upgrade first.")

    stats: dict[str, dict] = {
        k: {"created": 0, "skipped": 0, "errors": 0}
        for k in ("classes", "subclasses", "races", "monsters", "backgrounds", "feats")
    }

    def _existing_class(slug: str) -> bool:
        hit = local_content.resolve(slug, type="class_features", campaign_id=campaign_id)
        return bool(hit and hit[1] == "local-homebrew")

    def _existing_subclass(class_slug: str, sub_slug: str) -> bool:
        combined = f"{class_slug}__{sub_slug}"
        hit = local_content.resolve(combined, type="subclass_features", campaign_id=campaign_id)
        return bool(hit and hit[1] == "local-homebrew")

    def _existing_race(slug: str) -> bool:
        hit = local_content.resolve(slug, type="races", campaign_id=campaign_id)
        return bool(hit and hit[1] == "local-homebrew")

    def _existing_monster(slug: str) -> bool:
        hit = local_content.resolve(slug, type="monsters", campaign_id=campaign_id)
        return bool(hit and hit[1] == "local-homebrew")

    def _existing_background(slug: str) -> bool:
        hit = local_content.resolve(slug, type="backgrounds", campaign_id=campaign_id)
        return bool(hit and hit[1] == "local-homebrew")

    def _existing_feat(slug: str) -> bool:
        # v2.0.0: file-based homebrew tier. resolve() returns the highest-
        # priority hit including shipped SRD; we only want to mark "already
        # exists" if the campaign's own homebrew file claims the slug.
        hit = local_content.resolve(slug, type="feats", campaign_id=campaign_id)
        return bool(hit and hit[1] == "local-homebrew")

    # ── Classes ─────────────────────────────────────────────────────────
    for row in (body.get("classes") or [])[:200]:
        if not isinstance(row, dict):
            stats["classes"]["errors"] += 1
            continue
        try:
            name = _safe_str(row.get("name"), 120)
            slug = _slugify_for_subclass(name, max_len=60) or _safe_str(row.get("class_slug"), 60)
            if not name or not slug:
                stats["classes"]["errors"] += 1
                continue
            if _existing_class(slug):
                stats["classes"]["skipped"] += 1
                continue
            local_content.write_homebrew(
                {
                    "slug": slug,
                    "name": name,
                    "hit_die": _safe_int(row.get("hit_die"), 8),
                    "prof_armor": _safe_str(row.get("prof_armor"), 500),
                    "prof_weapons": _safe_str(row.get("prof_weapons"), 500),
                    "prof_tools": _safe_str(row.get("prof_tools"), 500),
                    "prof_saving_throws": _safe_str(row.get("prof_saving_throws"), 120),
                    "prof_skills": _safe_str(row.get("prof_skills"), 500),
                    "spellcasting_ability": _safe_str(row.get("spellcasting_ability"), 10).lower(),
                    "equipment": _safe_str(row.get("equipment"), 4000),
                    "features": row.get("features") if isinstance(row.get("features"), list) else [],
                    "spell_list": row.get("spell_list") if isinstance(row.get("spell_list"), list) else [],
                    "multiclass_prereq_abilities": row.get("multiclass_prereq_abilities") if isinstance(row.get("multiclass_prereq_abilities"), dict) else {},
                    "multiclass_prereq_mode": _safe_str(row.get("multiclass_prereq_mode") or "all", 8),
                    "multiclass_proficiencies": _safe_str(row.get("multiclass_proficiencies"), 500),
                    "resources": row.get("resources") if isinstance(row.get("resources"), list) else [],
                    "actions": [],
                    "system": "dnd5e",
                    "scope": f"campaign-{campaign_id}",
                    "source": "homebrew",
                    "owner": user.id,
                },
                type="class_features",
                scope=f"campaign-{campaign_id}",
            )
            stats["classes"]["created"] += 1
        except Exception:
            stats["classes"]["errors"] += 1

    # ── Subclasses ──────────────────────────────────────────────────────
    for row in (body.get("subclasses") or [])[:500]:
        if not isinstance(row, dict):
            stats["subclasses"]["errors"] += 1
            continue
        try:
            name = _safe_str(row.get("name"), 120)
            class_slug = _slugify_for_subclass(_safe_str(row.get("class_slug"), 60), max_len=60)
            sub_slug = _slugify_for_subclass(name, max_len=80) or _safe_str(row.get("sub_slug"), 80)
            if not name or not class_slug or not sub_slug:
                stats["subclasses"]["errors"] += 1
                continue
            if _existing_subclass(class_slug, sub_slug):
                stats["subclasses"]["skipped"] += 1
                continue
            local_content.write_homebrew(
                {
                    "slug": f"{class_slug}__{sub_slug}",
                    "name": name,
                    "class_slug": class_slug,
                    "subclass_flavor": _safe_str(row.get("flavor"), 4000),
                    "features": row.get("features") if isinstance(row.get("features"), list) else [],
                    "actions": [],
                    "system": "dnd5e",
                    "scope": f"campaign-{campaign_id}",
                    "source": "homebrew",
                    "owner": user.id,
                },
                type="subclass_features",
                scope=f"campaign-{campaign_id}",
            )
            stats["subclasses"]["created"] += 1
        except Exception:
            stats["subclasses"]["errors"] += 1

    # ── Races ───────────────────────────────────────────────────────────
    for row in (body.get("races") or [])[:200]:
        if not isinstance(row, dict):
            stats["races"]["errors"] += 1
            continue
        try:
            name = _safe_str(row.get("name"), 120)
            slug = _slugify_for_subclass(name, max_len=60) or _safe_str(row.get("race_slug"), 60)
            if not name or not slug:
                stats["races"]["errors"] += 1
                continue
            if _existing_race(slug):
                stats["races"]["skipped"] += 1
                continue
            local_content.write_homebrew(
                {
                    "slug": slug, "name": name,
                    "ability_bonuses": row.get("ability_bonuses") if isinstance(row.get("ability_bonuses"), list) else [],
                    "size": _safe_str(row.get("size"), 40),
                    "speed": _safe_int(row.get("speed"), 30),
                    "age": _safe_str(row.get("age"), 1000),
                    "alignment": _safe_str(row.get("alignment"), 1000),
                    "languages": _safe_str(row.get("languages"), 1000),
                    "traits": row.get("traits") if isinstance(row.get("traits"), list) else [],
                    "actions": [],
                    "system": "dnd5e",
                    "scope": f"campaign-{campaign_id}",
                    "source": "homebrew",
                    "owner": user.id,
                },
                type="races",
                scope=f"campaign-{campaign_id}",
            )
            stats["races"]["created"] += 1
        except Exception:
            stats["races"]["errors"] += 1

    # ── Monsters ────────────────────────────────────────────────────────
    for row in (body.get("monsters") or [])[:500]:
        if not isinstance(row, dict):
            stats["monsters"]["errors"] += 1
            continue
        try:
            name = _safe_str(row.get("name"), 120)
            slug = _slugify_for_subclass(name, max_len=80) or _safe_str(row.get("monster_slug"), 80)
            if not name or not slug:
                stats["monsters"]["errors"] += 1
                continue
            if _existing_monster(slug):
                stats["monsters"]["skipped"] += 1
                continue
            # Coalesce the 4 legacy split lists from the import payload into
            # the unified actions array with category labels.
            import re as _re
            _unified: list[dict] = []
            for _src_key, _cat in (
                ("actions", "action"),
                ("reactions", "reaction"),
                ("special_abilities", "special_ability"),
                ("legendary_actions", "legendary_action"),
            ):
                _list = row.get(_src_key)
                if not isinstance(_list, list):
                    continue
                for _entry in _list:
                    if not isinstance(_entry, dict):
                        continue
                    _nm = (_entry.get("name") or "").strip()
                    _slug_id = _re.sub(r"[^a-z0-9]+", "-", _nm.lower()).strip("-") or f"unnamed-{_cat}"
                    _unified.append({
                        "id": _entry.get("id") or _slug_id,
                        "name": _nm,
                        "desc": _entry.get("desc") or "",
                        "min_level": _entry.get("level") or 1,
                        "category": _cat,
                    })
            local_content.write_homebrew(
                {
                    "slug": slug, "name": name,
                    "size": _safe_str(row.get("size") or "Medium", 40),
                    "type": _safe_str(row.get("type") or "beast", 60).lower(),
                    "alignment": _safe_str(row.get("alignment"), 120),
                    "armor_class": _safe_int(row.get("armor_class"), 10),
                    "armor_desc": _safe_str(row.get("armor_desc"), 120),
                    "hit_points": _safe_int(row.get("hit_points"), 1),
                    "hit_dice": _safe_str(row.get("hit_dice"), 40),
                    "speed": row.get("speed") if isinstance(row.get("speed"), dict) else {"walk": 30},
                    "strength": _safe_int(row.get("strength"), 10),
                    "dexterity": _safe_int(row.get("dexterity"), 10),
                    "constitution": _safe_int(row.get("constitution"), 10),
                    "intelligence": _safe_int(row.get("intelligence"), 10),
                    "wisdom": _safe_int(row.get("wisdom"), 10),
                    "charisma": _safe_int(row.get("charisma"), 10),
                    "damage_vulnerabilities": _safe_str(row.get("damage_vulnerabilities"), 500),
                    "damage_resistances": _safe_str(row.get("damage_resistances"), 500),
                    "damage_immunities": _safe_str(row.get("damage_immunities"), 500),
                    "condition_immunities": _safe_str(row.get("condition_immunities"), 500),
                    "senses": _safe_str(row.get("senses"), 500),
                    "languages": _safe_str(row.get("languages"), 500),
                    "challenge_rating": _safe_str(row.get("challenge_rating") or "0", 20),
                    "actions": _unified,
                    "system": "dnd5e",
                    "scope": f"campaign-{campaign_id}",
                    "source": "homebrew",
                    "owner": user.id,
                },
                type="monsters",
                scope=f"campaign-{campaign_id}",
            )
            stats["monsters"]["created"] += 1
        except Exception:
            stats["monsters"]["errors"] += 1

    # ── Backgrounds ─────────────────────────────────────────────────────
    for row in (body.get("backgrounds") or [])[:200]:
        if not isinstance(row, dict):
            stats["backgrounds"]["errors"] += 1
            continue
        try:
            name = _safe_str(row.get("name"), 120)
            slug = _slugify_for_subclass(name, max_len=60) or _safe_str(row.get("background_slug"), 60)
            if not name or not slug:
                stats["backgrounds"]["errors"] += 1
                continue
            if _existing_background(slug):
                stats["backgrounds"]["skipped"] += 1
                continue
            local_content.write_homebrew(
                {
                    "slug": slug, "name": name,
                    "description": _safe_str(row.get("description"), 8000),
                    "skill_proficiencies": _safe_str(row.get("skill_proficiencies"), 500),
                    "tool_proficiencies": _safe_str(row.get("tool_proficiencies"), 500),
                    "languages": _safe_str(row.get("languages"), 500),
                    "equipment": _safe_str(row.get("equipment"), 4000),
                    "feature_name": _safe_str(row.get("feature_name"), 160),
                    "feature_desc": _safe_str(row.get("feature_desc"), 4000),
                    "actions": [],
                    "system": "dnd5e",
                    "scope": f"campaign-{campaign_id}",
                    "source": "homebrew",
                    "owner": user.id,
                },
                type="backgrounds",
                scope=f"campaign-{campaign_id}",
            )
            stats["backgrounds"]["created"] += 1
        except Exception:
            stats["backgrounds"]["errors"] += 1

    # ── Feats ───────────────────────────────────────────────────────────
    for row in (body.get("feats") or [])[:500]:
        if not isinstance(row, dict):
            stats["feats"]["errors"] += 1
            continue
        try:
            name = _safe_str(row.get("name"), 120)
            slug = _slugify_for_subclass(name, max_len=80) or _safe_str(row.get("feat_slug"), 80)
            if not name or not slug:
                stats["feats"]["errors"] += 1
                continue
            if _existing_feat(slug):
                stats["feats"]["skipped"] += 1
                continue
            # v2.0.0: write directly to the homebrew file volume.
            local_content.write_homebrew(
                {
                    "slug": slug, "name": name,
                    "prerequisite": _safe_str(row.get("prerequisite"), 500),
                    "desc": _safe_str(row.get("desc"), 8000),
                    "actions": [],
                    "system": "dnd5e",
                    "scope": f"campaign-{campaign_id}",
                    "source": "homebrew",
                    "owner": user.id,
                },
                type="feats",
                scope=f"campaign-{campaign_id}",
            )
            stats["feats"]["created"] += 1
        except Exception:
            stats["feats"]["errors"] += 1

    db.commit()
    totals = {
        "created": sum(s["created"] for s in stats.values()),
        "skipped": sum(s["skipped"] for s in stats.values()),
        "errors":  sum(s["errors"]  for s in stats.values()),
    }
    return {"ok": True, "stats": stats, "totals": totals}


@router.post("/campaign/{campaign_id}/members/{membership_id}/set_gm")
def set_member_gm(
    campaign_id: int,
    membership_id: int,
    is_gm: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Promote/demote a campaign member to/from co-GM. Any GM (primary,
    co-GM, or admin) of this campaign may toggle the flag."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    membership = (
        db.query(CampaignMembership)
        .filter(
            CampaignMembership.id == membership_id,
            CampaignMembership.campaign_id == campaign_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(404, "Member not found")
    membership.is_gm = bool(is_gm)
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings", status_code=303)


@router.post("/campaign/{campaign_id}/session/start")
async def start_session(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM (or admin) opens the tabletop to players. Idempotent: re-Starting
    an already-active session is a no-op except it refreshes started_at.

    Audio auto-start: when ``campaign.auto_play_playlist_id`` is set, the
    configured playlist begins playing the moment the session starts.
    ``auto_play_mode == 'order'`` plays the first track; ``'shuffle'``
    picks a random track. Any audio already playing is replaced. The
    auto-play side-effect tolerates errors (missing playlist, no tracks)
    silently — a broken auto-play config shouldn't block session start.
    """
    from datetime import datetime as _dt
    import random as _random
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    campaign.session_active = True
    campaign.session_started_at = _dt.utcnow()
    db.commit()
    await hub.broadcast(campaign_id, {"type": "session_started", "data": {}})

    # Auto-start audio if configured.
    if campaign.auto_play_playlist_id:
        from .audio_routes import _start_track_for_campaign
        playlist = (
            db.query(Playlist)
            .filter(
                Playlist.id == campaign.auto_play_playlist_id,
                Playlist.campaign_id == campaign_id,
            )
            .first()
        )
        if playlist and playlist.tracks:
            tracks = list(playlist.tracks)   # ordered by position
            if (campaign.auto_play_mode or "order").lower() == "shuffle":
                track = _random.choice(tracks)
            else:
                track = tracks[0]
            try:
                await _start_track_for_campaign(
                    db, campaign, track,
                    source="auto_start",
                    prev_reason="session_end",
                    user_id=user.id,
                )
            except Exception as exc:
                log.warning("Auto-play failed for campaign %s: %s", campaign_id, exc)

    # Auto-load the configured default encounter, if any. Same
    # tolerate-failures pattern as audio above — a broken default
    # encounter config shouldn't block session start. ``start_audio``
    # is False here because we just kicked off audio above (if
    # configured) via the campaign's auto-play setting; letting the
    # encounter clobber that would be surprising.
    if campaign.default_encounter_id:
        default_enc = (
            db.query(Encounter)
            .filter(
                Encounter.id == campaign.default_encounter_id,
                Encounter.campaign_id == campaign_id,
            )
            .first()
        )
        if default_enc:
            try:
                await _perform_encounter_load(
                    db, campaign, default_enc,
                    start_audio=False,
                    user_id=user.id,
                )
            except HTTPException as exc:
                log.warning(
                    "Default encounter %s skipped on session start for campaign %s: %s",
                    default_enc.id, campaign_id, exc.detail,
                )
            except Exception as exc:
                log.warning(
                    "Default encounter %s failed on session start for campaign %s: %s",
                    default_enc.id, campaign_id, exc,
                )

    return RedirectResponse(f"/campaign/{campaign_id}", status_code=303)


@router.post("/campaign/{campaign_id}/session/end")
async def end_session(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM (or admin) closes the tabletop. Players in the tabletop will be
    bounced back to the lobby; new players hitting the URL get the
    waiting page until the GM Starts again.

    Audio auto-stop: any audio still playing is stopped for everyone via
    the same path as the manual ``/audio/stop`` button.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    campaign.session_active = False
    db.commit()
    await hub.broadcast(campaign_id, {"type": "session_ended", "data": {}})

    # Stop any audio that's still playing. Idempotent — safe when nothing
    # is currently playing. ``reason='session_end'`` labels the in-flight
    # AudioPlayEvent (if any) so the history shows why the play ended.
    if campaign.now_playing_track_id is not None:
        from .audio_routes import _stop_audio_for_campaign
        try:
            await _stop_audio_for_campaign(db, campaign, reason="session_end")
        except Exception as exc:
            log.warning("Auto-stop audio failed for campaign %s: %s", campaign_id, exc)

    return RedirectResponse("/", status_code=303)


@router.get("/campaign/{campaign_id}/rolls", response_class=HTMLResponse)
def rolls_popout(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(404, "Not found")
    rolls = (
        db.query(DiceRoll)
        .filter(DiceRoll.campaign_id == campaign.id)
        .order_by(DiceRoll.created_at.desc())
        .limit(500)
        .all()
    )
    visible = [r for r in rolls if _filter_roll_for_user(r, user, campaign, db)]
    user_color_map, user_portrait_map, user_char_name_map = _build_user_maps(db, campaign)
    return templates.TemplateResponse(
        "rolls_popout.html",
        {
            "request": request,
            "user": user,
            "campaign": campaign,
            "rolls": visible,
            "is_gm": _user_is_gm(user, campaign, db),
            "user_color_map": user_color_map,
            "user_portrait_map": user_portrait_map,
            "user_char_name_map": user_char_name_map,
        },
    )


# ----------- API: tokens -----------

@router.post("/api/campaign/{campaign_id}/token/{token_id}/move")
async def move_token(
    campaign_id: int,
    token_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    body = await request.json()
    x = float(body.get("x", 0))
    y = float(body.get("y", 0))
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token or token.map.campaign_id != campaign_id:
        raise HTTPException(404, "Token not found")
    if not _user_can_move_token(db, user, token, campaign):
        raise HTTPException(403, "You can't move that token")
    token.x = x
    token.y = y
    db.commit()
    await hub.broadcast(
        campaign_id,
        {"type": "token_move", "data": {"id": token.id, "x": x, "y": y}},
    )
    return {"ok": True}


@router.post("/api/campaign/{campaign_id}/tokens")
async def create_token(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    body = await request.json()
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    if not campaign.active_map_id:
        raise HTTPException(400, "Campaign has no active map")

    tmpl_id = body.get("token_template_id")
    tmpl = None
    if tmpl_id:
        tmpl = db.query(TokenTemplate).filter(
            TokenTemplate.id == tmpl_id, TokenTemplate.campaign_id == campaign_id
        ).first()

    label = str(body.get("label") or (tmpl.name if tmpl else "Token"))[:120]
    image_url = body.get("image_url") or (tmpl.image_url if tmpl else None)

    t = Token(
        map_id=campaign.active_map_id,
        character_id=body.get("character_id"),
        token_template_id=tmpl_id if tmpl else None,
        label=label,
        color=str(body.get("color", "#cc3333"))[:20],
        image_url=image_url,
        x=float(body.get("x", 100)),
        y=float(body.get("y", 100)),
        size=int(body.get("size", 1)),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    await hub.broadcast(
        campaign_id,
        {"type": "token_add", "data": _token_dict(t)},
    )
    return _token_dict(t)


@router.post("/api/campaign/{campaign_id}/character/{char_id}/place-token")
async def place_character_token(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Place a character's token on the active map. GM-only as of v0.63.0
    (previously the character's owner could also call this; players no
    longer add/remove tokens themselves).

    Optional body: ``{x: float, y: float}`` to override the default
    placement coordinates. The browser client passes the world-space
    center of the GM's current viewport so tokens land where the GM is
    looking instead of at the (often offscreen) geometric center of the
    map. Non-browser callers can omit the body and get the legacy
    map-center default.

    If the character already has a token on this map it is replaced.
    Token image is pre-filled from the character's portrait if one is set."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    if not campaign.active_map_id:
        raise HTTPException(400, "No active map")
    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")

    # Remove any existing token for this character on the active map first.
    existing = (
        db.query(Token)
        .filter(Token.character_id == char_id, Token.map_id == campaign.active_map_id)
        .first()
    )
    if existing:
        old_id = existing.id
        db.delete(existing)
        db.flush()
        await hub.broadcast(campaign_id, {"type": "token_delete", "data": {"id": old_id}})

    active_map = db.query(Map).filter(Map.id == campaign.active_map_id).first()
    gsize = active_map.grid_size_px if active_map else 70
    # Legacy fallback: geometric center of the map, snapped to the grid.
    fallback_x = round((active_map.width_px / 2) / gsize) * gsize if active_map else 0
    fallback_y = round((active_map.height_px / 2) / gsize) * gsize if active_map else 0
    # If the client sent viewport-center coords, snap them to the grid
    # so the new token sits cleanly on a cell instead of mid-tile.
    if isinstance(body, dict) and "x" in body and "y" in body:
        try:
            cx = round(float(body["x"]) / gsize) * gsize
            cy = round(float(body["y"]) / gsize) * gsize
        except (TypeError, ValueError):
            cx, cy = fallback_x, fallback_y
    else:
        cx, cy = fallback_x, fallback_y

    t = Token(
        map_id=campaign.active_map_id,
        character_id=char.id,
        controller_user_id=char.owner_user_id,
        label=char.name[:120],
        color="#cc3333",
        image_url=char.portrait_url,
        x=float(cx),
        y=float(cy),
        size=1,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    await hub.broadcast(campaign_id, {"type": "token_add", "data": _token_dict(t)})
    return _token_dict(t)


@router.delete("/api/campaign/{campaign_id}/character/{char_id}/token")
async def remove_character_token(
    campaign_id: int,
    char_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Remove a character's token from the active map. GM-only as of
    v0.63.0 (previously the character's owner could also call this)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not campaign.active_map_id:
        return {"ok": True, "removed": False}
    token = (
        db.query(Token)
        .filter(Token.character_id == char_id, Token.map_id == campaign.active_map_id)
        .first()
    )
    if not token:
        return {"ok": True, "removed": False}
    token_id = token.id
    db.delete(token)
    db.commit()
    await hub.broadcast(campaign_id, {"type": "token_delete", "data": {"id": token_id}})
    return {"ok": True, "removed": True}


@router.delete("/api/campaign/{campaign_id}/tokens/{token_id}")
async def delete_token(
    campaign_id: int,
    token_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token or token.map.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    db.delete(token)
    db.commit()
    await hub.broadcast(campaign_id, {"type": "token_delete", "data": {"id": token_id}})
    return {"ok": True}


def _encounter_to_dict(e: Encounter) -> dict:
    """Encounter projection used by the GM listing UIs.

    Includes the lightweight summary fields the Battle drawer + campaign
    settings need to render rows, plus the preview fields Phase 5 added
    (``token_names``, ``map_name``) for the on-hover tooltip and the
    ``tags`` array for client-side filtering / chip rendering."""
    payload = e.payload or {}
    tokens = payload.get("tokens") or []
    initiative = payload.get("initiative") or []
    # Cap names returned to keep payload bounded; the tooltip elides
    # the rest as " + N more". Order matches the saved token order so
    # the GM sees combatants in roughly the same sequence they're
    # rendered on the canvas.
    token_names = [
        (t.get("label_override") or "Token") for t in tokens[:25]
    ]
    extra = max(0, len(tokens) - len(token_names))
    return {
        "id": e.id,
        "name": e.name,
        "description": e.description or "",
        "map_id": e.map_id,
        "map_name": e.map.name if e.map else None,
        "map_image_url": e.map.image_url if e.map else None,
        "map_thumbnail_url": e.map.thumbnail_url if e.map else None,
        "auto_play_playlist_id": e.auto_play_playlist_id,
        "auto_play_mode": e.auto_play_mode or "order",
        "auto_play_playlist_name": (
            e.auto_play_playlist.name if e.auto_play_playlist else None
        ),
        "tags": list(e.tags or []),
        "folder": e.folder or "",
        "stop_audio_on_load": bool(e.stop_audio_on_load),
        "use_spawn_points": bool(e.use_spawn_points),
        "spawn_points": dict(e.spawn_points or {}),
        "token_count": len(tokens),
        "token_names": token_names,
        "token_names_extra": extra,
        "initiative_count": len(initiative),
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _parse_tags(value) -> list[str]:
    """Coerce a tags input (list or comma-separated string) into a
    deduplicated list of short trimmed strings. Used by both the create
    and PATCH endpoints so the wire format is flexible."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [t.strip() for t in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = [str(t).strip() for t in value]
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for t in items:
        if not t:
            continue
        t = t[:40]
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= 20:
            break
    return out


@router.get("/api/campaign/{campaign_id}/encounters")
def list_encounters(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """List the GM's saved encounters for a campaign. GM-only.

    Each row carries an ``is_current`` flag so the Battle drawer can pin
    the currently-running encounter (the one most recently loaded via
    ``_perform_encounter_load``) to the top of its panel summary.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    rows = (
        db.query(Encounter)
        .filter(Encounter.campaign_id == campaign_id)
        .order_by(Encounter.created_at.desc())
        .all()
    )
    current_id = campaign.current_encounter_id
    out = []
    for e in rows:
        d = _encounter_to_dict(e)
        d["is_current"] = (current_id is not None and e.id == current_id)
        out.append(d)
    return out


def _snapshot_encounter_payload(db: Session, campaign: Campaign) -> dict:
    """Capture the current token state + battle hub state into the JSON
    payload shape used by the encounters table.

    Both GM-owned and player-controlled tokens are captured (the latter
    flagged by a non-null ``controller_user_id`` + ``character_id``).
    The load flow applies Option B for player tokens — restore only if
    the character has no token on the target map yet — so capturing
    them is non-destructive to ongoing player positions.
    """
    tokens_out = []
    if campaign.active_map_id:
        rows = (
            db.query(Token)
            .filter(Token.map_id == campaign.active_map_id)
            .all()
        )
        for t in rows:
            tokens_out.append({
                "template_id": t.token_template_id,
                "character_id": t.character_id,
                "controller_user_id": t.controller_user_id,
                "label_override": t.label or "",
                "color_override": t.color or "",
                "image_url": t.image_url,
                "size": int(t.size or 1),
                "x": float(t.x or 0),
                "y": float(t.y or 0),
                "is_hidden": bool(t.is_hidden),
            })
    # Battle hub state is opaque to the server — JS PUTs the canonical
    # shape via /api/campaign/.../battle. We snapshot it whole so a load
    # restores combatant order, current turn, round number, HP, …
    # exactly as the GM had it.
    battle_state = hub.get_battle(campaign.id) or {}
    return {
        "tokens": tokens_out,
        "battle_state": battle_state,
    }


@router.post("/api/campaign/{campaign_id}/encounters")
async def create_encounter(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Save an encounter. GM-only.

    Two creation modes:

    1. **Snapshot the current state** (the original Phase 2 path).
       Body: ``{name, description?, tags?, map_id?, auto_play_playlist_id?,
       auto_play_mode?}``. When ``payload`` is absent we capture the
       active map's tokens + the in-memory battle hub state. ``map_id``
       and ``auto_play_playlist_id`` override the active-map / now-playing
       defaults so the GM can bind the snapshot to a different map or
       playlist than the live ones (useful when staging tokens on map A
       but the encounter belongs to map B).

    2. **Build from blank** — Phase-6 prep workflow.
       Body: ``{name, payload: {tokens: [], battle_state: {}}, map_id,
       auto_play_playlist_id?, auto_play_mode?, description?, tags?}``.
       When ``payload`` is present we trust it as-is, don't touch the
       live tabletop state, and create a draft the GM can fill in later
       with 💾 Update once they're staged on the bound map.
    """
    body = await request.json()
    name = str(body.get("name") or "").strip()[:160]
    if not name:
        raise HTTPException(400, "Encounter name required")
    description = str(body.get("description") or "").strip()

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")

    if "payload" in body:
        # Build-from-blank path. Accept the caller's payload verbatim so
        # they can start with an empty bundle and fill in later.
        raw_payload = body.get("payload") or {}
        if not isinstance(raw_payload, dict):
            raise HTTPException(400, "payload must be an object")
        payload = {
            "tokens": list(raw_payload.get("tokens") or []),
            "battle_state": raw_payload.get("battle_state") or {},
        }
    else:
        payload = _snapshot_encounter_payload(db, campaign)

    # Map binding: explicit > campaign.active_map_id. Validate that any
    # explicit map_id belongs to this campaign so the GM can't bind to
    # another campaign's map.
    if "map_id" in body and body["map_id"] is not None:
        try:
            map_id_val = int(body["map_id"])
        except (TypeError, ValueError):
            raise HTTPException(400, "Invalid map_id")
        m = db.query(Map).filter(Map.id == map_id_val, Map.campaign_id == campaign_id).first()
        if not m:
            raise HTTPException(404, "Map not found in this campaign")
        bound_map_id = m.id
    else:
        bound_map_id = campaign.active_map_id

    # Playlist binding: explicit > inferred from currently-playing track.
    auto_play_mode = str(body.get("auto_play_mode") or campaign.auto_play_mode or "order")
    if auto_play_mode not in ("order", "shuffle", "song"):
        auto_play_mode = "order"
    auto_play_playlist_id: Optional[int] = None
    if "auto_play_playlist_id" in body:
        v = body["auto_play_playlist_id"]
        if v is not None and v != "":
            try:
                pl_id = int(v)
            except (TypeError, ValueError):
                raise HTTPException(400, "Invalid auto_play_playlist_id")
            pl = (
                db.query(Playlist)
                .filter(Playlist.id == pl_id, Playlist.campaign_id == campaign_id)
                .first()
            )
            if not pl:
                raise HTTPException(404, "Playlist not found in this campaign")
            auto_play_playlist_id = pl.id
    elif campaign.now_playing_track_id:
        track = (
            db.query(PlaylistTrack)
            .filter(PlaylistTrack.id == campaign.now_playing_track_id)
            .first()
        )
        if track:
            auto_play_playlist_id = track.playlist_id

    use_spawn_points = bool(body.get("use_spawn_points", False))
    raw_spawns = body.get("spawn_points")
    spawn_points: dict = {}
    if isinstance(raw_spawns, dict):
        for key, coord in raw_spawns.items():
            if not isinstance(coord, dict):
                continue
            try:
                spawn_points[str(int(key))] = {
                    "x": float(coord.get("x", 0)),
                    "y": float(coord.get("y", 0)),
                }
            except (TypeError, ValueError):
                continue

    enc = Encounter(
        campaign_id=campaign_id,
        name=name,
        description=description,
        map_id=bound_map_id,
        auto_play_playlist_id=auto_play_playlist_id,
        auto_play_mode=auto_play_mode,
        auto_play_track_id=int(body["auto_play_track_id"]) if body.get("auto_play_track_id") else None,
        payload=payload,
        tags=_parse_tags(body.get("tags")),
        use_spawn_points=use_spawn_points,
        spawn_points=spawn_points,
        folder=str(body.get("folder") or "").strip()[:120],
        stop_audio_on_load=bool(body.get("stop_audio_on_load", False)),
    )
    db.add(enc)
    db.commit()
    db.refresh(enc)
    return _encounter_to_dict(enc)


@router.patch("/api/campaign/{campaign_id}/encounters/{encounter_id}")
async def update_encounter_meta(
    campaign_id: int,
    encounter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Rename / re-describe a saved encounter. GM-only.

    Body: ``{name?, description?}``. Either or both may be provided;
    omitted fields are left untouched. Empty/whitespace ``name`` is
    rejected — the library row would render as a blank line otherwise.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    enc = (
        db.query(Encounter)
        .filter(Encounter.id == encounter_id, Encounter.campaign_id == campaign_id)
        .first()
    )
    if not enc:
        raise HTTPException(404, "Encounter not found")

    if "name" in body:
        new_name = str(body.get("name") or "").strip()[:160]
        if not new_name:
            raise HTTPException(400, "Encounter name cannot be empty")
        enc.name = new_name
    if "description" in body:
        enc.description = str(body.get("description") or "").strip()
    if "tags" in body:
        enc.tags = _parse_tags(body.get("tags"))
    if "map_id" in body:
        v = body.get("map_id")
        if v is None or v == "":
            enc.map_id = None
        else:
            try:
                map_id_val = int(v)
            except (TypeError, ValueError):
                raise HTTPException(400, "Invalid map_id")
            m = (
                db.query(Map)
                .filter(Map.id == map_id_val, Map.campaign_id == campaign_id)
                .first()
            )
            if not m:
                raise HTTPException(404, "Map not found in this campaign")
            enc.map_id = m.id
    if "auto_play_playlist_id" in body:
        v = body.get("auto_play_playlist_id")
        if v is None or v == "":
            enc.auto_play_playlist_id = None
        else:
            try:
                pl_id = int(v)
            except (TypeError, ValueError):
                raise HTTPException(400, "Invalid auto_play_playlist_id")
            pl = (
                db.query(Playlist)
                .filter(Playlist.id == pl_id, Playlist.campaign_id == campaign_id)
                .first()
            )
            if not pl:
                raise HTTPException(404, "Playlist not found in this campaign")
            enc.auto_play_playlist_id = pl.id
    if "auto_play_mode" in body:
        mode = str(body.get("auto_play_mode") or "order")
        if mode not in ("order", "shuffle"):
            raise HTTPException(400, "auto_play_mode must be 'order' or 'shuffle'")
        enc.auto_play_mode = mode
    if "folder" in body:
        enc.folder = str(body.get("folder") or "").strip()[:120]
    if "stop_audio_on_load" in body:
        enc.stop_audio_on_load = bool(body.get("stop_audio_on_load"))
    if "use_spawn_points" in body:
        enc.use_spawn_points = bool(body.get("use_spawn_points"))
    if "spawn_points" in body:
        # Wholesale replace — the per-character endpoint below is the
        # incremental path; this branch is for PATCH callers that want
        # to set the whole dict at once (e.g. duplicating from another
        # encounter, or clearing all spawns with ``{}``).
        raw_spawns = body.get("spawn_points") or {}
        if not isinstance(raw_spawns, dict):
            raise HTTPException(400, "spawn_points must be an object")
        normalised: dict = {}
        for key, coord in raw_spawns.items():
            if not isinstance(coord, dict):
                continue
            try:
                normalised[str(int(key))] = {
                    "x": float(coord.get("x", 0)),
                    "y": float(coord.get("y", 0)),
                }
            except (TypeError, ValueError):
                continue
        enc.spawn_points = normalised

    db.commit()
    db.refresh(enc)
    return _encounter_to_dict(enc)


@router.post("/api/campaign/{campaign_id}/encounters/{encounter_id}/spawn")
async def set_encounter_spawn(
    campaign_id: int,
    encounter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Set or clear a single character's spawn point on an encounter.
    GM-only. Body: ``{character_id: int, x?: float, y?: float}``. When
    ``x`` and ``y`` are both numeric the spawn is recorded; otherwise
    the entry for ``character_id`` is cleared. Used by the click-to-set
    flow in the encounter row's edit form."""
    body = await request.json()
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    enc = (
        db.query(Encounter)
        .filter(Encounter.id == encounter_id, Encounter.campaign_id == campaign_id)
        .first()
    )
    if not enc:
        raise HTTPException(404, "Encounter not found")
    try:
        char_id = int(body.get("character_id"))
    except (TypeError, ValueError):
        raise HTTPException(400, "character_id required")
    char = (
        db.query(Character)
        .filter(Character.id == char_id, Character.campaign_id == campaign_id)
        .first()
    )
    if not char:
        raise HTTPException(404, "Character not found in this campaign")

    spawns = dict(enc.spawn_points or {})
    key = str(char_id)
    x_raw = body.get("x")
    y_raw = body.get("y")
    if x_raw is None or y_raw is None:
        spawns.pop(key, None)
        out = None
    else:
        try:
            spawns[key] = {"x": float(x_raw), "y": float(y_raw)}
        except (TypeError, ValueError):
            raise HTTPException(400, "Invalid x or y")
        out = spawns[key]
    enc.spawn_points = spawns
    db.commit()
    db.refresh(enc)
    return _encounter_to_dict(enc)


@router.post("/api/campaign/{campaign_id}/encounters/{encounter_id}/duplicate")
def duplicate_encounter(
    campaign_id: int,
    encounter_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Copy a saved encounter into a new row with a " (copy)" suffix on
    the name. GM-only. Useful for spinning up variants of the same setup
    ("Goblin Ambush — Dawn", "Goblin Ambush — Night") without recapturing
    the whole bundle each time.

    The copy is a fresh row with new ``created_at`` / ``updated_at``;
    everything else (payload, map, playlist, tags, notes) is duplicated."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    src = (
        db.query(Encounter)
        .filter(Encounter.id == encounter_id, Encounter.campaign_id == campaign_id)
        .first()
    )
    if not src:
        raise HTTPException(404, "Encounter not found")

    new_name = (src.name + " (copy)")[:160]
    copy = Encounter(
        campaign_id=campaign_id,
        name=new_name,
        description=src.description or "",
        map_id=src.map_id,
        auto_play_playlist_id=src.auto_play_playlist_id,
        auto_play_mode=src.auto_play_mode or "order",
        payload=src.payload or {},
        tags=list(src.tags or []),
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return _encounter_to_dict(copy)


@router.post("/api/campaign/{campaign_id}/encounters/{encounter_id}/update")
async def overwrite_encounter(
    campaign_id: int,
    encounter_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Re-snapshot the current campaign state into an existing encounter.
    GM-only.

    Use this when a saved encounter ("Goblin Ambush") evolves between
    sessions and the GM wants to overwrite the bundle in place instead
    of creating a new sibling row. Name + description + ``created_at``
    are kept; ``payload`` + ``map_id`` + ``auto_play_playlist_id`` +
    ``auto_play_mode`` are replaced from the current state. ``updated_at``
    auto-bumps via the ``onupdate=func.now()`` clause on the column.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    enc = (
        db.query(Encounter)
        .filter(Encounter.id == encounter_id, Encounter.campaign_id == campaign_id)
        .first()
    )
    if not enc:
        raise HTTPException(404, "Encounter not found")

    enc.payload = _snapshot_encounter_payload(db, campaign)
    enc.map_id = campaign.active_map_id
    enc.auto_play_mode = campaign.auto_play_mode or "order"
    enc.auto_play_playlist_id = None
    if campaign.now_playing_track_id:
        track = (
            db.query(PlaylistTrack)
            .filter(PlaylistTrack.id == campaign.now_playing_track_id)
            .first()
        )
        if track:
            enc.auto_play_playlist_id = track.playlist_id

    db.commit()
    db.refresh(enc)
    return _encounter_to_dict(enc)


@router.post("/api/campaign/{campaign_id}/encounters/{encounter_id}/delete")
def delete_encounter(
    campaign_id: int,
    encounter_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Delete a saved encounter. GM-only. No broadcast — the library is
    a GM-only view, so other clients don't care."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    enc = (
        db.query(Encounter)
        .filter(Encounter.id == encounter_id, Encounter.campaign_id == campaign_id)
        .first()
    )
    if not enc:
        raise HTTPException(404, "Encounter not found")
    db.delete(enc)
    db.commit()
    return {"ok": True}


async def _perform_encounter_load(
    db: Session,
    campaign: Campaign,
    enc: Encounter,
    *,
    start_audio: bool,
    user_id: Optional[int],
) -> dict:
    """Two-pass strict load shared by the explicit Load endpoint and the
    session-start auto-load hook. See ``load_encounter`` for the
    semantics — this helper is the implementation; the route is a thin
    wrapper that parses the body + permission-checks. Raises
    ``HTTPException`` for caller-fixable errors so the route can let
    them propagate verbatim.
    """
    payload = enc.payload or {}
    target_map_id = enc.map_id or campaign.active_map_id
    if not target_map_id:
        raise HTTPException(400, "Encounter has no map and campaign has no active map")
    map_switched = bool(enc.map_id and enc.map_id != campaign.active_map_id)
    campaign_id = campaign.id

    # ── Pass 1: clear every token on the target map ──
    # Strict semantics (v0.73.0): only the tokens described by the
    # encounter exist after the load. Players whose characters aren't
    # in the saved bundle (no snapshot entry AND no spawn point) have
    # their tokens removed too.
    all_tokens = (
        db.query(Token)
        .filter(Token.map_id == target_map_id)
        .all()
    )
    deleted_ids = [t.id for t in all_tokens]
    for t in all_tokens:
        db.delete(t)
    db.flush()

    # ── Pass 2a: switch the active map if the encounter binds a new one ──
    if map_switched:
        campaign.active_map_id = enc.map_id
        db.flush()

    # Mark this encounter as the campaign's currently-running one so the
    # Battle drawer can keep it pinned in the UI even while collapsed.
    campaign.current_encounter_id = enc.id
    db.flush()

    # ── Pass 2b: create the new tokens from the payload ──
    # When ``use_spawn_points`` is true the encounter's spawn_points
    # dict drives player placement and the snapshot's player entries
    # are ignored. Otherwise we fall back to the snapshot's player
    # tokens. GM tokens (no ``character_id``) always come from payload.
    warnings: list[str] = []
    created_tokens: list[Token] = []
    use_spawns = bool(enc.use_spawn_points)
    spawn_map: dict = dict(enc.spawn_points or {}) if use_spawns else {}

    for tok_def in (payload.get("tokens") or []):
        char_id = tok_def.get("character_id")
        if char_id:
            # Player token. Skip the snapshot entry when spawn-points
            # mode is on — the spawn pass below covers player placement.
            if use_spawns:
                continue
            char = db.query(Character).filter(Character.id == char_id).first()
            if not char:
                warnings.append(
                    f"Player character #{char_id} no longer exists; skipping their saved token."
                )
                continue
            new_token = Token(
                map_id=target_map_id,
                character_id=char.id,
                controller_user_id=char.owner_user_id,
                label=char.name[:120],
                color=(tok_def.get("color_override") or char.color or "#cc3333")[:20],
                image_url=tok_def.get("image_url") or char.portrait_url,
                x=float(tok_def.get("x", 100)),
                y=float(tok_def.get("y", 100)),
                size=int(tok_def.get("size", 1) or 1),
                is_hidden=bool(tok_def.get("is_hidden", False)),
            )
            db.add(new_token)
            created_tokens.append(new_token)
            continue
        tmpl_id = tok_def.get("template_id")
        tmpl = None
        if tmpl_id:
            tmpl = (
                db.query(TokenTemplate)
                .filter(
                    TokenTemplate.id == tmpl_id,
                    TokenTemplate.campaign_id == campaign_id,
                )
                .first()
            )
            if not tmpl:
                warnings.append(
                    f"Token template #{tmpl_id} missing; falling back to manual token."
                )
        label = (tok_def.get("label_override") or (tmpl.name if tmpl else "Token"))[:120]
        color = (tok_def.get("color_override") or "#cc3333")[:20]
        image_url = tok_def.get("image_url") or (tmpl.image_url if tmpl else None)
        new_token = Token(
            map_id=target_map_id,
            token_template_id=tmpl.id if tmpl else None,
            label=label,
            color=color,
            image_url=image_url,
            x=float(tok_def.get("x", 100)),
            y=float(tok_def.get("y", 100)),
            size=int(tok_def.get("size", 1) or 1),
            is_hidden=bool(tok_def.get("is_hidden", False)),
        )
        db.add(new_token)
        created_tokens.append(new_token)

    # ── Pass 2c: place player tokens from spawn_points (when enabled) ──
    if use_spawns:
        gsize = 1
        target_map_obj = db.query(Map).filter(Map.id == target_map_id).first()
        if target_map_obj and target_map_obj.grid_size_px:
            gsize = max(1, int(target_map_obj.grid_size_px))
        for key, coord in spawn_map.items():
            if not isinstance(coord, dict):
                continue
            try:
                char_id = int(key)
                x = round(float(coord["x"]) / gsize) * gsize
                y = round(float(coord["y"]) / gsize) * gsize
            except (TypeError, ValueError, KeyError):
                continue
            char = (
                db.query(Character)
                .filter(Character.id == char_id, Character.campaign_id == campaign_id)
                .first()
            )
            if not char:
                warnings.append(
                    f"Spawn-point character #{char_id} no longer exists; skipping."
                )
                continue
            new_token = Token(
                map_id=target_map_id,
                character_id=char.id,
                controller_user_id=char.owner_user_id,
                label=char.name[:120],
                color=char.color or "#cc3333",
                image_url=char.portrait_url,
                x=float(x),
                y=float(y),
                size=1,
            )
            db.add(new_token)
            created_tokens.append(new_token)

    db.commit()
    for t in created_tokens:
        db.refresh(t)

    # ── Pass 3: restore battle hub state ──
    battle_state = payload.get("battle_state") or {}
    if battle_state:
        hub.set_battle(campaign_id, battle_state)

    # ── Broadcasts ──
    if map_switched:
        # Map change is a big enough scene shift that we ask clients to
        # reload; their existing canvas wasn't built to swap maps in
        # place. The reload picks up the new active_map + tokens via the
        # standard SSR path and reconnects the WS, which seeds the new
        # battle state from the hub.
        await hub.broadcast(
            campaign_id,
            {"type": "map_change", "data": {"map_id": target_map_id}},
        )
    else:
        # Same map — surgical token_delete + token_add broadcasts keep
        # every player's canvas in sync without a reload.
        for tid in deleted_ids:
            await hub.broadcast(
                campaign_id, {"type": "token_delete", "data": {"id": tid}}
            )
        for t in created_tokens:
            await hub.broadcast(
                campaign_id, {"type": "token_add", "data": _token_dict(t)}
            )
        if battle_state:
            await hub.broadcast(
                campaign_id, {"type": "battle_update", "data": battle_state}
            )

    # ── Audio behaviour on load ──
    # Three-way decision when ``start_audio`` is true:
    #   1. ``auto_play_playlist_id`` set → start that playlist (takes
    #      precedence over the stop-on-load flag).
    #   2. No playlist + ``stop_audio_on_load`` true → stop current
    #      audio so the GM gets a clean silent transition.
    #   3. No playlist + ``stop_audio_on_load`` false (default) →
    #      leave the currently-playing audio alone (continue).
    # Each branch tolerates missing/broken state with a non-fatal
    # warning rather than failing the whole load.
    if start_audio and enc.auto_play_playlist_id:
        playlist = (
            db.query(Playlist)
            .filter(
                Playlist.id == enc.auto_play_playlist_id,
                Playlist.campaign_id == campaign_id,
            )
            .first()
        )
        if not playlist:
            warnings.append("Saved playlist missing; audio skipped.")
        else:
            tracks = list(playlist.tracks)
            track: Optional[PlaylistTrack] = None
            mode = enc.auto_play_mode or "order"
            if tracks:
                if mode == "shuffle":
                    import random
                    track = random.choice(tracks)
                elif mode == "song" and enc.auto_play_track_id:
                    track = next((t for t in tracks if t.id == enc.auto_play_track_id), tracks[0])
                else:
                    track = tracks[0]
            if track:
                # Deferred import: audio_routes imports from realtime + models,
                # so importing it lazily keeps this module's load-time graph
                # free of audio-side dependencies.
                from .audio_routes import _start_track_for_campaign
                await _start_track_for_campaign(
                    db, campaign, track,
                    source="auto_start",
                    prev_reason="skipped",
                    user_id=user_id,
                )
    elif start_audio and enc.stop_audio_on_load and campaign.now_playing_track_id:
        # No playlist for this encounter AND the GM asked for silence;
        # stop whatever's currently playing. ``_stop_audio_for_campaign``
        # is idempotent so the now_playing_track_id guard is just to
        # skip the no-op call when nothing is playing.
        from .audio_routes import _stop_audio_for_campaign
        await _stop_audio_for_campaign(db, campaign, reason="skipped")

    return {
        "ok": True,
        "map_switched": map_switched,
        "tokens_created": len(created_tokens),
        "tokens_deleted": len(deleted_ids),
        "warnings": warnings,
        # v2.4.6: return the canonical post-load battle state so the GM
        # client (which is authoritative and ignores the
        # ``battle_update`` WS broadcast) can hydrate its local
        # init-tracker view to match what the server just put into the
        # hub. Without this, the GM keeps a stale localStorage battle
        # after Load — exactly the bug a v2.3.44-portrait demo user
        # hit when they'd populated the tracker pre-v2.4.3.
        "battle_state": battle_state or None,
    }


@router.post("/api/campaign/{campaign_id}/encounters/{encounter_id}/load")
async def load_encounter(
    campaign_id: int,
    encounter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Two-pass strict load. GM-only.

    Pass 1 — Delete **every** token on the **target map** (the
    encounter's bound map, or the campaign's active map if the encounter
    has no map). Strict semantics: after a load, only tokens described
    by the encounter remain. Player tokens for characters not in the
    encounter are removed.

    Pass 2 — If the encounter binds a different map, switch
    ``campaign.active_map_id`` and broadcast ``map_change`` so connected
    clients reload onto the new map. Then recreate tokens from the
    encounter:

    * **GM tokens** from the saved payload.
    * **Player tokens**:
      - When ``use_spawn_points`` is true, one token per entry in
        ``encounter.spawn_points`` (placed at the spawn coord). The
        saved snapshot's player tokens are ignored.
      - Otherwise, the saved snapshot's player tokens are used
        verbatim (positions captured at save time).

    Body (optional): ``{start_audio: bool = true}``. When true and the
    encounter has an ``auto_play_playlist_id``, audio auto-starts via the
    existing ``_start_track_for_campaign`` helper.

    Implementation lives in ``_perform_encounter_load`` so the
    session-start auto-load hook can call the same code path.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    start_audio = bool(body.get("start_audio", True))

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    enc = (
        db.query(Encounter)
        .filter(Encounter.id == encounter_id, Encounter.campaign_id == campaign_id)
        .first()
    )
    if not enc:
        raise HTTPException(404, "Encounter not found")
    return await _perform_encounter_load(
        db, campaign, enc, start_audio=start_audio, user_id=user.id,
    )


@router.patch("/api/campaign/{campaign_id}/token/{token_id}")
async def update_token(
    campaign_id: int,
    token_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    body = await request.json()
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token or token.map.campaign_id != campaign_id:
        raise HTTPException(404, "Token not found")
    if "label" in body:
        token.label = str(body["label"])[:120]
    if "is_hidden" in body:
        token.is_hidden = bool(body["is_hidden"])
    if "controller_user_id" in body:
        val = body["controller_user_id"]
        token.controller_user_id = int(val) if val else None
    if "color" in body:
        token.color = str(body["color"])[:20]
    db.commit()
    await hub.broadcast(campaign_id, {"type": "token_update", "data": _token_dict(token)})
    return _token_dict(token)


@router.post("/api/campaign/{campaign_id}/token/{token_id}/image")
async def upload_token_image(
    campaign_id: int,
    token_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    import uuid
    from pathlib import Path as _Path

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token or token.map.campaign_id != campaign_id:
        raise HTTPException(404, "Token not found")
    allowed = {"image/png", "image/jpeg", "image/webp", "image/gif"}
    if image.content_type not in allowed:
        raise HTTPException(400, "Unsupported image type")
    data = await image.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Image too large (>5 MB)")
    token_dir = _Path(__file__).resolve().parent.parent / "static" / "uploads" / "tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    ext = _Path(image.filename or "img.png").suffix.lower() or ".png"
    fname = f"{uuid.uuid4().hex}{ext}"
    (token_dir / fname).write_bytes(data)
    token.image_url = f"/static/uploads/tokens/{fname}"
    db.commit()
    await hub.broadcast(campaign_id, {"type": "token_update", "data": _token_dict(token)})
    return {"image_url": token.image_url}


def _token_dict(t: Token) -> dict:
    return {
        "id": t.id,
        "label": t.label,
        "color": t.color,
        "x": t.x,
        "y": t.y,
        "size": t.size,
        "character_id": t.character_id,
        "controller_user_id": t.controller_user_id,
        "image_url": t.image_url,
        "is_hidden": t.is_hidden,
        "token_template_id": t.token_template_id,
    }


# ----------- API: dice -----------

@router.post("/api/campaign/{campaign_id}/roll")
async def roll_dice(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    body = await request.json()
    expr = str(body.get("expression", "")).strip()
    visibility_str = str(body.get("visibility", "public")).lower()
    note = str(body.get("note", ""))[:200]
    skip_roll_state = bool(body.get("skip_roll_state"))
    try:
        visibility = Visibility(visibility_str)
    except ValueError:
        raise HTTPException(400, "Invalid visibility")
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    # Look up the rolling user's character so we can (a) apply roll_state
    # to single-d20 expressions and (b) attribute the roll in the log.
    # Explicit ``character_id`` in the body wins (lets a GM roll for a
    # specific char); falls back to the user's first character.
    _char = None
    explicit_char_id = body.get("character_id")
    if explicit_char_id:
        try:
            _char = (
                db.query(Character)
                .filter(Character.id == int(explicit_char_id),
                        Character.campaign_id == campaign_id)
                .first()
            )
        except (TypeError, ValueError):
            _char = None
    if _char is None:
        _char = (
            db.query(Character)
            .filter(Character.campaign_id == campaign_id, Character.owner_user_id == user.id)
            .first()
        )

    # v2.2.0: apply roll_state to single-d20 expressions before rolling.
    # Manual 2d20kh1 / 2d20kl1 are detected but left unchanged; the note
    # is annotated either way so the log distinguishes auto vs manual.
    roll_state_applied = ""
    if not skip_roll_state:
        rs = (_char.sheet or {}).get("roll_state") if _char else None
        expr, roll_state_applied = _apply_roll_state(expr, rs)
    note_suffix = _roll_state_note_suffix(roll_state_applied)
    if note_suffix:
        note = (note + note_suffix)[:200]

    try:
        result = dice_mod.roll(expr)
    except dice_mod.DiceParseError as e:
        raise HTTPException(400, str(e))
    rec = DiceRoll(
        campaign_id=campaign_id,
        user_id=user.id,
        expression=expr,
        breakdown=result.breakdown,
        total=result.total,
        visibility=visibility,
        note=note,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    _char_name   = _char.name        if _char else None
    _portrait_url = _char.portrait_url if _char else None
    _membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id, CampaignMembership.user_id == user.id)
        .first()
    )
    _player_color = (
        _membership.color if _membership and _membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    _user_color = (_char.color if _char and _char.color else _player_color)
    await hub.broadcast(
        campaign_id,
        {
            "type": "roll",
            "data": {
                "id": rec.id,
                "user_id": user.id,
                "user_name": user.display_name,
                "char_name": _char_name,
                "user_color": _user_color,
                "portrait_url": _portrait_url,
                "expression": rec.expression,
                "breakdown": rec.breakdown,
                "total": rec.total,
                "visibility": rec.visibility.value,
                "note": rec.note,
                "created_at": rec.created_at.isoformat() if rec.created_at else None,
                "roll_state_applied": roll_state_applied or None,
            },
        },
    )
    return {"ok": True, "total": rec.total, "breakdown": rec.breakdown,
            "roll_state_applied": roll_state_applied or None}


@router.post("/api/campaign/{campaign_id}/member_color")
async def set_member_color(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM sets a roll-log highlight color for any campaign member (including themselves)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    body = await request.json()
    target_user_id = int(body.get("user_id", 0))
    color = str(body.get("color", "")).strip()[:20] or None  # None clears the color
    if target_user_id == campaign.gm_user_id:
        campaign.gm_color = color
    else:
        membership = (
            db.query(CampaignMembership)
            .filter(CampaignMembership.campaign_id == campaign_id, CampaignMembership.user_id == target_user_id)
            .first()
        )
        if not membership:
            raise HTTPException(404, "Member not found")
        membership.color = color
    db.commit()
    await hub.broadcast(
        campaign_id,
        {"type": "member_color_update", "data": {"user_id": target_user_id, "color": color}},
    )
    return {"ok": True}


@router.post("/api/campaign/{campaign_id}/character/{char_id}/color")
async def set_character_color(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM sets a roll-log color on a character. Overrides the player's assigned color."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    body = await request.json()
    color = str(body.get("color", "")).strip()[:20] or None
    char.color = color
    db.commit()
    # Broadcast so live tabletop updates immediately
    await hub.broadcast(
        campaign_id,
        {
            "type": "character_color_update",
            "data": {
                "char_id": char.id,
                "owner_user_id": char.owner_user_id,
                "color": color,
            },
        },
    )
    return {"ok": True}


_VALID_RING_STYLES = {"solid", "dashed", "double", "glow", "spiked"}


@router.post("/api/campaign/{campaign_id}/character/{char_id}/ring-style")
async def set_character_ring_style(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Player or GM sets the token ring color and style for a character."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if char.owner_user_id != user.id and not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "Not your character")
    body = await request.json()
    raw_color = str(body.get("color", "")).strip()[:20]
    if raw_color:
        char.color = raw_color
    ring_style = str(body.get("ring_style", "solid")).strip()
    if ring_style not in _VALID_RING_STYLES:
        ring_style = "solid"
    char.ring_style = ring_style
    db.commit()
    await hub.broadcast(
        campaign_id,
        {
            "type": "character_ring_update",
            "data": {
                "char_id": char.id,
                "color": char.color,
                "ring_style": ring_style,
            },
        },
    )
    return {"ok": True}


# ----------- API: roll requests -----------

def _resolve_stat_modifier(sheet: dict, template: str, stat_key: str) -> tuple[int, str]:
    """Return (modifier, display_label) by looking up *stat_key* in a D&D 5e sheet.

    stat_key forms:
      "str_save" … "cha_save"   → saving throw (adds prof if proficient)
      "str_check" … "cha_check" → raw ability modifier
      Exact skill name           → skill modifier (adds prof/expertise)
      Anything else / non-5e    → (0, "")
    """
    if not stat_key or template != "dnd5e":
        return 0, ""

    abilities = sheet.get("abilities") or {}
    saving_throws = sheet.get("saving_throws") or {}
    skills = sheet.get("skills") or {}
    prof = int(sheet.get("proficiency_bonus") or 2)

    _AB_LONG = {"str": "STR", "dex": "DEX", "con": "CON",
                "int": "INT", "wis": "WIS", "cha": "CHA"}

    def ab_mod(ab: str) -> int:
        return (int(abilities.get(ab, 10)) - 10) // 2

    # Saving throw: "str_save", "con_save", …
    for short, long in _AB_LONG.items():
        if stat_key == f"{short}_save":
            mod = ab_mod(long)
            if saving_throws.get(long, False):
                mod += prof
            label = f"{long} Save{'(prof)' if saving_throws.get(long) else ''}"
            return mod, label
        if stat_key in (f"{short}_check", f"{short}_mod"):
            return ab_mod(long), f"{long} Check"

    # Skill: exact name e.g. "Perception", "Stealth"
    skill_data = skills.get(stat_key)
    if skill_data:
        ab = skill_data.get("ability", "STR")
        mod = ab_mod(ab)
        if skill_data.get("expertise", False):
            mod += prof * 2
            suffix = " (exp)"
        elif skill_data.get("proficient", False):
            mod += prof
            suffix = " (prof)"
        else:
            suffix = ""
        return mod, f"{stat_key}{suffix}"

    return 0, ""


@router.post("/api/campaign/{campaign_id}/roll_request")
async def create_roll_request(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM posts a roll-request card to the roll log so players can respond."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")

    body = await request.json()
    label = str(body.get("label", "")).strip()[:200]
    if not label:
        raise HTTPException(400, "label is required")

    stat_key = str(body.get("stat_key", "") or "").strip()[:60] or None
    base_expr = str(body.get("base_expression", "1d20") or "1d20").strip()[:60] or "1d20"
    dc_raw = body.get("dc")
    dc = int(dc_raw) if dc_raw is not None and str(dc_raw).strip() else None
    visibility_str = str(body.get("visibility", "public")).lower()
    try:
        visibility = Visibility(visibility_str)
    except ValueError:
        visibility = Visibility.PUBLIC

    # Target-player filter. Empty list (default) keeps the legacy
    # broadcast-to-everyone behaviour. Non-empty list narrows the prompt to
    # specific campaign members; the validated names are echoed back in the
    # WS payload so the GM's roll-log card can show who was targeted.
    raw_targets = body.get("target_user_ids") or []
    if not isinstance(raw_targets, list):
        raw_targets = []
    target_ids: list[int] = []
    for t in raw_targets[:32]:
        try:
            target_ids.append(int(t))
        except (TypeError, ValueError):
            continue
    target_user_ids: list[int] = []
    target_user_names: list[str] = []
    if target_ids:
        member_rows = (
            db.query(User)
            .join(CampaignMembership, CampaignMembership.user_id == User.id)
            .filter(
                CampaignMembership.campaign_id == campaign_id,
                User.id.in_(target_ids),
            )
            .all()
        )
        by_id = {u.id: u for u in member_rows}
        for tid in target_ids:
            u = by_id.get(tid)
            if u and u.id not in target_user_ids:
                target_user_ids.append(u.id)
                target_user_names.append(u.display_name)

    req = RollRequest(
        campaign_id=campaign_id,
        created_by_user_id=user.id,
        label=label,
        base_expression=base_expr,
        stat_key=stat_key,
        dc=dc,
        visibility=visibility,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    await hub.broadcast(
        campaign_id,
        {
            "type": "roll_request",
            "data": {
                "id": req.id,
                "label": req.label,
                "stat_key": req.stat_key,
                "base_expression": req.base_expression,
                "dc": req.dc,
                "visibility": req.visibility.value,
                "created_by_name": user.display_name,
                "created_by_user_id": user.id,
                "target_user_ids": target_user_ids,
                "target_user_names": target_user_names,
            },
        },
    )
    return {"ok": True, "id": req.id}


@router.post("/api/campaign/{campaign_id}/roll_request/{req_id}/respond")
async def respond_roll_request(
    campaign_id: int,
    req_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Player (or GM acting as a token) clicks the Roll button in a roll-request card.

    The server resolves the stat modifier from the chosen character sheet, builds
    the final expression, rolls it, and broadcasts a standard ``roll`` WS message.
    A DC pass/fail note is appended when the request has a DC set.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    roll_req = db.query(RollRequest).filter(
        RollRequest.id == req_id,
        RollRequest.campaign_id == campaign_id,
    ).first()
    if not roll_req:
        raise HTTPException(404, "Roll request not found")

    body = await request.json()
    char_id = body.get("character_id")

    # Load character — GMs may roll for any campaign character; players only theirs
    char: Optional[Character] = None
    if char_id:
        char = db.query(Character).filter(
            Character.id == char_id,
            Character.campaign_id == campaign_id,
        ).first()
        if not char:
            raise HTTPException(404, "Character not found")
        is_gm = _user_is_gm(user, campaign, db)
        if not is_gm and char.owner_user_id != user.id:
            raise HTTPException(403, "Not your character")

    # Resolve stat modifier from sheet
    mod, stat_label = (0, "")
    if char and roll_req.stat_key:
        mod, stat_label = _resolve_stat_modifier(
            char.sheet or {}, char.template, roll_req.stat_key
        )

    # Build final expression
    base = roll_req.base_expression or "1d20"
    if mod > 0:
        final_expr = f"{base}+{mod}"
    elif mod < 0:
        final_expr = f"{base}{mod}"
    else:
        final_expr = base

    # Roll
    try:
        result = dice_mod.roll(final_expr)
    except dice_mod.DiceParseError as e:
        raise HTTPException(400, f"Bad expression '{final_expr}': {e}")

    # Build a descriptive note
    char_name = char.name if char else None
    note_parts = [f"→ {roll_req.label}"]
    if stat_label:
        note_parts.append(stat_label)
    if roll_req.dc is not None:
        outcome = "✓ Pass" if result.total >= roll_req.dc else "✗ Fail"
        note_parts.append(f"DC {roll_req.dc} — {outcome}")
    note = " | ".join(note_parts)[:200]

    rec = DiceRoll(
        campaign_id=campaign_id,
        user_id=user.id,
        expression=final_expr,
        breakdown=result.breakdown,
        total=result.total,
        visibility=roll_req.visibility,
        note=note,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    # Resolve portrait / color for broadcast
    _membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id, CampaignMembership.user_id == user.id)
        .first()
    )
    _player_color = (
        _membership.color if _membership and _membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    _portrait_url = char.portrait_url if char else None
    _user_color = (char.color if char and char.color else _player_color)

    await hub.broadcast(
        campaign_id,
        {
            "type": "roll",
            "data": {
                "id": rec.id,
                "user_id": user.id,
                "user_name": user.display_name,
                "char_name": char_name,
                "user_color": _user_color,
                "portrait_url": _portrait_url,
                "expression": rec.expression,
                "breakdown": rec.breakdown,
                "total": rec.total,
                "visibility": rec.visibility.value,
                "note": rec.note,
                "created_at": rec.created_at.isoformat() if rec.created_at else None,
            },
        },
    )
    return {"ok": True, "total": rec.total, "breakdown": rec.breakdown}


# ----------- API: cast spell -----------

@router.post("/api/campaign/{campaign_id}/cast_spell")
async def cast_spell(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Cast a spell from a character's sheet.

    Decrements the matching spell slot (when ``spell_level >= 1``) and
    broadcasts a ``spell_cast`` WebSocket message that other clients render
    as an interactive card in the roll log. Cantrips (level 0) skip the
    slot check entirely.

    Returns 409 ``{"error": "no_slot", ...}`` when the slot is empty so the
    caller can show a non-blocking toast instead of a roll-log entry.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    spell_index = int(body.get("spell_index", -1))
    if char_id <= 0 or spell_index < 0:
        raise HTTPException(400, "character_id and spell_index are required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id,
        Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    if char.template == "dnd5e":
        normalize_dnd5e_sheet(sheet)
    spells = list(sheet.get("spells") or [])
    if spell_index >= len(spells):
        raise HTTPException(404, "Spell not found")
    spell = dict(spells[spell_index] or {})
    spell_level = int(spell.get("level") or 0)

    # Allow upcasting via an optional slot_level override; default to spell.level
    slot_level_raw = body.get("slot_level")
    slot_level = int(slot_level_raw) if slot_level_raw is not None and str(slot_level_raw).strip() else spell_level
    if slot_level < spell_level:
        slot_level = spell_level

    # Determine which class's slots to deduct from.  Body may pass
    # ``class_slug`` explicitly; otherwise fall back to the spell's tagged
    # class, then the primary (highest-level) class on the sheet.
    body_slug = (body.get("class_slug") or "").strip().lower()
    spell_class_slug = (spell.get("class") or "").strip().lower()
    primary_slug = _class_slug(sheet.get("class") or "")
    cslug = body_slug or spell_class_slug or primary_slug

    # Decrement slot when this is a leveled spell (cantrips are free)
    updated_slot = None
    if spell_level >= 1:
        all_slots = dict(sheet.get("spell_slots") or {})
        per_class = dict(all_slots.get(cslug) or {})
        slot_key = str(slot_level)
        slot = dict(per_class.get(slot_key) or {"total": 0, "used": 0})
        total = int(slot.get("total") or 0)
        used = int(slot.get("used") or 0)
        if total <= 0 or used >= total:
            return JSONResponse(
                status_code=409,
                content={
                    "error": "no_slot",
                    "level": slot_level,
                    "class_slug": cslug,
                    "spell_name": spell.get("name", ""),
                },
            )
        slot["used"] = used + 1
        per_class[slot_key] = slot
        all_slots[cslug] = per_class
        sheet["spell_slots"] = all_slots
        char.sheet = sheet
        db.commit()
        updated_slot = {
            "class_slug": cslug,
            "level": slot_level,
            "total": total,
            "used": slot["used"],
        }

    # v2.6.1: Phase 4 over-budget gate. Compute the economy slot up-front
    # so we can decide whether this cast needs a Layer B confirm modal
    # before any state mutation. Players hitting an already-used slot get
    # 409 ``over_budget`` and the client opens the modal; on Confirm the
    # client retries with ``override: true`` and we proceed. GM clicks
    # skip the gate entirely (rules-authority bypass per the plan) but
    # still flow through the same ``over_budget`` tag in the broadcast so
    # the Layer C audit badge fires.
    slot_for_economy = _casting_time_to_economy(spell.get("casting_time", ""))
    was_used = _is_slot_used(campaign_id, char.id, slot_for_economy)
    user_is_gm = _user_is_gm(user, campaign, db)
    override = bool(body.get("override"))
    if was_used and not user_is_gm and not override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": slot_for_economy,
            "char_name": char.name,
            "source": "spell",
            "label": spell.get("name", ""),
        })

    # Resolve caster display info (same shape as roll broadcasts)
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id, CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    cast_id = uuid.uuid4().hex[:12]

    payload = {
        "id": cast_id,
        "caster_user_id": user.id,
        "caster_user_name": user.display_name,
        "caster_user_color": caster_color,
        "caster_portrait_url": char.portrait_url,
        "caster_char_id": char.id,
        "caster_char_name": char.name,
        "spell_index": spell_index,
        "spell_name": spell.get("name", ""),
        "spell_level": spell_level,
        "slot_level": slot_level,
        "over_budget": was_used,
        "over_budget_slot": slot_for_economy if was_used else "",
        "spell_school": spell.get("school", ""),
        "spell_casting_time": spell.get("casting_time", ""),
        "spell_range": spell.get("range", ""),
        "spell_duration": spell.get("duration", ""),
        "spell_components": spell.get("components", ""),
        "spell_concentration": bool(spell.get("concentration")),
        "spell_ritual": bool(spell.get("ritual")),
        "spell_damage": spell.get("damage", ""),
        "spell_save_ability": spell.get("save_ability", ""),
        "spell_healing": spell.get("healing", ""),
        "spell_aoe_targets": max(1, int(spell.get("aoe_targets") or 1)),
        "spell_attack_roll": bool(spell.get("attack_roll")),
        "spell_desc": spell.get("desc", "") or spell.get("description", ""),
        # Structured action descriptors — present when the spell came from the
        # file-based local_content tier with an `actions: list[Action]` array.
        # Client's renderActionButtons consumes this directly; if empty the
        # client synthesizes a single Action from the legacy fields above.
        "actions": spell.get("actions") or [],
    }

    # Register heal claims so /apply_healing can validate and roll server-side
    if payload["spell_healing"]:
        _purge_heal_claims()
        _heal_claims[cast_id] = {
            "dice": payload["spell_healing"],
            "max_targets": payload["spell_aoe_targets"],
            "claimed": set(),        # user_ids who have already claimed
            "campaign_id": campaign_id,
            "expires": _time.time() + 8 * 3600,
        }

    await hub.broadcast(campaign_id, {"type": "spell_cast", "data": payload})
    if updated_slot is not None:
        await hub.broadcast(campaign_id, {
            "type": "spell_slot_update",
            "data": {
                "character_id": char.id,
                "class_slug": updated_slot["class_slug"],
                "level": updated_slot["level"],
                "total": updated_slot["total"],
                "used": updated_slot["used"],
            },
        })
    # v2.5.5: full-sheet → init chip sync. Slot was derived up-front
    # for the Phase 4 gate; reuse it here so the idempotence in
    # _mark_battle_economy keeps an over-budget cast from re-flipping
    # the chip (it's already used — that's why we got here).
    await _mark_battle_economy(campaign_id, char.id, slot_for_economy)
    return {"ok": True, "id": cast_id, "slot": updated_slot, "over_budget": was_used}


# ----------- API: use class feature (Phase 3 action-economy) -----------

@router.post("/api/campaign/{campaign_id}/use_feature")
async def use_feature(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Announce a class-feature use and mark its action-economy slot.

    Powers the "Class abilities" panel on the full character sheet
    (sheet_dnd5e.html) and any future mini-sheet equivalents. Body:
    ``{character_id, feature_key, option_key?, label?, desc?}``.

    The slot is **always** re-derived server-side from
    ``_feature_economy_slot(feature_key, option_key)`` — client claims
    are ignored to keep an attacker from minting bonus-action chips
    they shouldn't have. Returns 404 if the feature isn't in the
    curated table. ``label`` and ``desc`` are display-only and just
    get echoed into the ``feature_used`` WS broadcast for the roll
    log; they default to the feature_key/option_key if missing.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    feature_key = str(body.get("feature_key") or "").strip().lower()
    option_key_raw = body.get("option_key")
    option_key = str(option_key_raw).strip().lower() if option_key_raw else None
    if char_id <= 0 or not feature_key:
        raise HTTPException(400, "character_id and feature_key are required")

    slot = _feature_economy_slot(feature_key, option_key)
    if slot is None:
        raise HTTPException(404, f"Unknown feature: {feature_key}")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    feature_label = (body.get("label") or feature_key.replace("-", " ").title())[:160]
    if option_key:
        feature_label = f"{feature_label}: {(option_key or '').replace('-', ' ').title()}"
    feature_desc = str(body.get("desc") or "")[:400]

    # v2.6.1: Phase 4 over-budget gate. "free" features (Action Surge,
    # Divine Smite, Reckless Attack) never trigger the gate — they grant
    # rather than consume. See cast_spell for the matching pattern.
    was_used = _is_slot_used(campaign_id, char.id, slot)
    user_is_gm = _user_is_gm(user, campaign, db)
    override = bool(body.get("override"))
    if was_used and not user_is_gm and not override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": slot,
            "char_name": char.name,
            "source": "feature",
            "label": feature_label,
        })

    # Resolve display info for the broadcast — same pattern as cast_spell.
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": feature_label,
            "feature_desc": feature_desc,
            "source": "class-feature",
            "remaining": 0,
            "max": 0,
            "over_budget": was_used,
            "over_budget_slot": slot if was_used else "",
        },
    })

    # slot == "free" means the feature doesn't consume an economy slot
    # (Action Surge / Divine Smite / Reckless Attack); the helper short-
    # circuits on anything that isn't action/bonus/reaction.
    await _mark_battle_economy(campaign_id, char.id, slot)

    return {"ok": True, "slot": slot, "feature_label": feature_label, "over_budget": was_used}


# ----------- Death save state machine (v2.1.0) -----------
#
# 5e death saving throws: when a character drops to 0 HP they enter the
# "dying" state and roll a d20 each turn. 10+ = success, <10 = failure;
# 3 successes → stable, 3 failures → dead. Natural 20 regains 1 HP +
# wakes them up; natural 1 counts as two failures. Damage while at 0 HP
# auto-ticks a failure (two on a crit); damage that exceeds max HP at 0
# is instant death (massive damage rule).
#
# Every endpoint that mutates ``Character.sheet["hp"]["current"]`` MUST
# route through ``_apply_hp_change`` so the state machine stays in
# lockstep with HP. Direct ``sheet["hp"]["current"] = …`` assignments
# bypass the machine and leave the character in an inconsistent state.

# Valid death save status values. Kept as a constant so the override and
# stabilize endpoints can validate against the same set.
_DEATH_SAVE_STATUSES = ("alive", "dying", "stable", "dead")


def _apply_hp_change(
    char: Character,
    new_current: int,
    *,
    is_damage: bool = False,
    is_crit: bool = False,
    damage_amount: int = 0,
) -> dict:
    """Set ``Character.sheet["hp"]["current"]`` to ``new_current`` and run
    the death save state machine. The single source of truth for HP
    transitions in v2.1.0+.

    Args:
        char: The Character row to mutate (modified in-place).
        new_current: Target HP value after the change. Clamped at 0.
        is_damage: True if the change is a damage source. Enables the
            damage-at-0 auto-failure tick and the massive-damage rule.
            Callers that just *set* HP (manual sheet save, GM edit, /heal)
            should leave this False.
        is_crit: True for critical-hit damage. Ticks two failures instead
            of one when applied to a dying character.
        damage_amount: Raw damage value applied this event (before temp
            HP absorption). Used to evaluate the massive-damage threshold.

    Returns:
        A dict with the post-mutation state for the caller to echo back
        and broadcast:
            - hp: {current, max, temp}
            - death_saves: {status, successes, failures}
            - status_changed: bool
            - became_dying / became_dead: bool flags for the caller
              to surface in the log / toast
    """
    sheet = dict(char.sheet or {})
    hp = dict(sheet.get("hp") or {})
    ds = dict(sheet.get("death_saves") or {})

    max_hp = int(hp.get("max") or 0)
    old_current = int(hp.get("current") or 0)
    old_status = ds.get("status") or "alive"
    successes = int(ds.get("successes") or 0)
    failures = int(ds.get("failures") or 0)

    new_status = old_status
    became_dying = False
    became_dead = False

    new_current = max(0, int(new_current))

    if new_current > 0:
        # HP positive — healing or set. Wake from any non-alive state.
        # v2.1.1: this includes "dead" — healing auto-revives. The earlier
        # design ("dead stays dead, GM override required") proved confusing
        # in practice: the user healing a character is usually the GM, and
        # forcing them through a second action to clear the dead flag was
        # unhelpful. If a table wants strict revivify-spell semantics they
        # can keep the character at 0 HP and use the override to mark them
        # alive at 1 HP rather than healing them through it.
        if old_status in ("dying", "stable", "dead"):
            new_status = "alive"
            successes = 0
            failures = 0
    else:
        # new_current == 0
        if old_status == "alive":
            # Crossing into 0 HP. Massive-damage rule: if remaining
            # damage past 0 ≥ max_hp, instant death.
            if is_damage and max_hp > 0:
                remaining = max(0, damage_amount - old_current)
                if remaining >= max_hp:
                    new_status = "dead"
                    became_dead = True
                    successes = 0
                    failures = 0
                else:
                    new_status = "dying"
                    became_dying = True
                    successes = 0
                    failures = 0
            else:
                # Non-damage set to 0 (manual edit). Treat as dying with
                # zero counters; no auto-failure.
                new_status = "dying"
                became_dying = True
                successes = 0
                failures = 0
        elif old_status == "dying":
            if is_damage:
                # Per RAW: any damage at 0 HP = 1 failure (2 on crit);
                # damage_amount ≥ max_hp = instant death.
                if max_hp > 0 and damage_amount >= max_hp:
                    new_status = "dead"
                    became_dead = True
                    successes = 0
                    failures = 0
                else:
                    failures += 2 if is_crit else 1
                    if failures >= 3:
                        new_status = "dead"
                        became_dead = True
                        successes = 0
                        failures = 0
        elif old_status == "stable":
            if is_damage:
                # Damage to a stable character drops them back to dying
                # with an immediate failure tick.
                if max_hp > 0 and damage_amount >= max_hp:
                    new_status = "dead"
                    became_dead = True
                    successes = 0
                    failures = 0
                else:
                    new_status = "dying"
                    became_dying = True
                    failures = 2 if is_crit else 1
                    successes = 0
        # ``dead`` stays dead until GM override.

    hp["current"] = new_current
    hp.setdefault("max", 0)
    hp.setdefault("temp", 0)
    ds["status"] = new_status
    ds["successes"] = successes
    ds["failures"] = failures

    sheet["hp"] = hp
    sheet["death_saves"] = ds
    char.sheet = sheet

    return {
        "hp": hp,
        "death_saves": ds,
        "status_changed": new_status != old_status,
        "became_dying": became_dying,
        "became_dead": became_dead,
    }


def _set_death_save_state(
    char: Character,
    *,
    status: str | None = None,
    successes: int | None = None,
    failures: int | None = None,
) -> dict:
    """Manually patch parts of the death save state without touching HP.
    Used by the GM override + stabilize endpoints. Returns the updated
    ``death_saves`` dict for the caller to broadcast."""
    sheet = dict(char.sheet or {})
    ds = dict(sheet.get("death_saves") or {"status": "alive", "successes": 0, "failures": 0})
    if status is not None:
        ds["status"] = status
    if successes is not None:
        ds["successes"] = max(0, int(successes))
    if failures is not None:
        ds["failures"] = max(0, int(failures))
    sheet["death_saves"] = ds
    char.sheet = sheet
    return ds


# ----------- Roll-state (advantage/disadvantage) — v2.2.0 -----------
#
# Per-character "roll state" toggled via the tri-state pill on the
# mini-sheet / full sheet. When set, the server upgrades single-d20
# expressions sent through /roll and /attack to 2d20kh1 (advantage) or
# 2d20kl1 (disadvantage) before rolling. Manual buttons that produce
# 2d20kh1 / 2d20kl1 directly bypass the auto-upgrade (the regex only
# matches single-d20). See docs/plans/advantage-disadvantage.md.

# Matches exactly a single 1d20 with optional +N/-N modifiers and
# whitespace. Rejects 1d20a / 1d20d (manual shorthand), 2d20kh1/kl1
# (manual long form), and any multi-dice expression (damage, ability
# gen, etc.). Group 1 captures the trailing modifier string.
_SINGLE_D20_RE = _re.compile(
    r'^\s*1d20((?:\s*[+-]\s*\d+)*)\s*$',
    _re.IGNORECASE,
)

# Manual adv/dis detection in the *submitted* expression (before any
# server upgrade). Matches both the long form (2d20kh1 / 2d20kl1) and
# the shorthand (1d20a / 1d20d) that dice.py expands.
_MANUAL_ADV_RE = _re.compile(r'(?i)\b(?:2d20kh1|1d20a)\b')
_MANUAL_DIS_RE = _re.compile(r'(?i)\b(?:2d20kl1|1d20d)\b')


def _apply_roll_state(
    expression: str,
    roll_state: dict | None,
) -> tuple[str, str]:
    """Upgrade a single-d20 expression to 2d20kh1 (advantage) or 2d20kl1
    (disadvantage) per the character's stored ``roll_state.value``.

    Returns ``(new_expression, applied)`` where ``applied`` is:

    - ``"auto_advantage"`` / ``"auto_disadvantage"`` — server upgraded
    - ``"manual_advantage"`` / ``"manual_disadvantage"`` — caller submitted
      a manual 2d20kh1 / 1d20a / 2d20kl1 / 1d20d expression
    - ``""`` — no upgrade and no manual flag

    Manual takes precedence over auto: if the submitted expression is
    already adv/dis, ``new_expression`` is the original and ``applied``
    reflects the manual form.
    """
    expr = expression or ""

    # 1) Detect manual adv/dis on the original expression first. If
    # the caller explicitly picked adv/dis, that wins — we don't double
    # up, and we tag the log with "manual ...".
    if _MANUAL_ADV_RE.search(expr):
        return expr, "manual_advantage"
    if _MANUAL_DIS_RE.search(expr):
        return expr, "manual_disadvantage"

    # 2) Auto upgrade only when the character has a roll_state set AND
    # the expression is a single-d20 form.
    value = None
    if isinstance(roll_state, dict):
        value = roll_state.get("value")
    if value not in ("advantage", "disadvantage"):
        return expr, ""

    m = _SINGLE_D20_RE.match(expr)
    if not m:
        return expr, ""
    modifiers = m.group(1) or ""
    if value == "advantage":
        return "2d20kh1" + modifiers, "auto_advantage"
    return "2d20kl1" + modifiers, "auto_disadvantage"


def _roll_state_note_suffix(applied: str) -> str:
    """Human-readable tag for ``applied`` from _apply_roll_state, suitable
    for appending to the roll's ``note`` field. Empty string for no-op."""
    return {
        "auto_advantage":     " (auto advantage)",
        "auto_disadvantage":  " (auto disadvantage)",
        "manual_advantage":   " (manual advantage)",
        "manual_disadvantage":" (manual disadvantage)",
    }.get(applied, "")


# ----------- API: apply healing from roll-log card -----------

@router.post("/api/campaign/{campaign_id}/apply_healing")
async def apply_healing(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Roll healing dice for a spell cast and apply the result to the calling
    user's character.  For AOE spells each user may only claim once; the
    charge counter is enforced server-side via ``_heal_claims``."""
    body = await request.json()
    cast_id = str(body.get("cast_id") or "")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    claim = _heal_claims.get(cast_id)
    if not claim or claim["campaign_id"] != campaign_id:
        raise HTTPException(404, "Unknown spell cast — it may have expired")

    claimed: set = claim["claimed"]
    max_targets: int = claim["max_targets"]

    if user.id in claimed:
        raise HTTPException(409, "You have already claimed healing from this spell")
    if max_targets > 1 and len(claimed) >= max_targets:
        raise HTTPException(409, "All healing charges have been used")

    # Find the user's character in this campaign (first owned character)
    char = (
        db.query(Character)
        .filter(Character.campaign_id == campaign_id, Character.owner_user_id == user.id)
        .first()
    )
    if not char:
        raise HTTPException(404, "You have no character in this campaign")

    # Roll the healing dice server-side
    try:
        r = dice_mod.roll(claim["dice"])
        rolled = r.total
        breakdown = r.breakdown
    except Exception:
        rolled = 0
        breakdown = ""

    # Apply HP through the death-save state machine (heals wake the
    # character from dying/stable per v2.1.0 design).
    hp_before = char.sheet.get("hp") or {}
    hp_cur = int(hp_before.get("current") or 0)
    hp_max = int(hp_before.get("max") or 0)
    new_cur = min(hp_max, hp_cur + rolled) if hp_max > 0 else (hp_cur + rolled)
    result = _apply_hp_change(char, new_cur)
    db.commit()

    # Track claim
    claimed.add(user.id)
    claimed_count = len(claimed)

    new_hp = result["hp"]
    await hub.broadcast(campaign_id, {
        "type": "heal_applied",
        "data": {
            "cast_id": cast_id,
            "char_id": char.id,
            "char_name": char.name,
            "healer_name": user.display_name,
            "dice": claim["dice"],
            "rolled": rolled,
            "breakdown": breakdown,
            "new_hp": new_hp,
            "claimed_count": claimed_count,
            "max_targets": max_targets,
        },
    })
    if result["status_changed"]:
        await hub.broadcast(campaign_id, {
            "type": "character_death_save",
            "data": {
                "character_id": char.id,
                "status": result["death_saves"]["status"],
                "successes": int(result["death_saves"]["successes"]),
                "failures": int(result["death_saves"]["failures"]),
                "hp": new_hp,
                "source": "heal",
            },
        })
    return {"ok": True, "rolled": rolled, "breakdown": breakdown, "new_hp": new_hp,
            "claimed_count": claimed_count, "max_targets": max_targets}


# ----------- API: short / long rest -----------

@router.post("/api/campaign/{campaign_id}/character/{char_id}/rest")
async def rest_character(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Apply a short or long rest to a character.

    Body: ``{"type": "short" | "long"}``.

    Short rest: spend one hit die, roll d{HD}+CON, recover that much HP
    (capped at max), decrement hit_dice.current. Returns 409 if no hit
    dice are left.

    Long rest: HP→max, Temp HP cleared, hit_dice.current += max(1, ⌊max/2⌋)
    capped at max, every spell_slots[*].used reset to 0. Broadcasts a
    spell_slot_update WS message per slot level so any open mini-sheet or
    full sheet rerenders its pips.
    """
    body = await request.json()
    rest_type = str(body.get("type", "")).strip().lower()
    if rest_type not in ("short", "long"):
        raise HTTPException(400, "type must be 'short' or 'long'")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    if char.template == "dnd5e":
        normalize_dnd5e_sheet(sheet)
    hp = dict(sheet.get("hp") or {})
    hp_max = int(hp.get("max") or 0)
    hp_cur = int(hp.get("current") or 0)
    hd = dict(sheet.get("hit_dice") or {})
    hd_max = int(hd.get("max") if hd.get("max") is not None else (sheet.get("level") or 1))
    hd_cur = int(hd.get("current") if hd.get("current") is not None else hd_max)

    # Refill matching trackable resources. Long rest refills 'short' + 'long';
    # short rest only refills 'short'. Resources with reset='none' (manual
    # chat-only feature with a counter) are never auto-refilled.
    resources_before = list(sheet.get("resources") or [])
    refilled_resources: list[dict] = []
    new_resources: list[dict] = []
    for r in resources_before:
        if not isinstance(r, dict):
            new_resources.append(r)
            continue
        reset_kind = str(r.get("reset") or "").strip().lower()
        should_refill = (
            reset_kind == "short" and rest_type in ("short", "long")
        ) or (
            reset_kind == "long" and rest_type == "long"
        )
        if should_refill and int(r.get("max") or 0) > 0:
            updated = {**r, "current": int(r.get("max") or 0)}
            new_resources.append(updated)
            refilled_resources.append(updated)
        else:
            new_resources.append(r)
    sheet["resources"] = new_resources

    if rest_type == "long":
        long_rest_new_cur = hp_max if hp_max > 0 else hp_cur
        hp["temp"] = 0
        hd["max"] = hd_max
        hd["current"] = min(hd_max, hd_cur + max(1, hd_max // 2)) if hd_max > 0 else hd_cur
        # Reset slots across every class's nested slot map.
        slots = dict(sheet.get("spell_slots") or {})
        new_slots: dict = {}
        broadcasts: list[tuple[str, int, int]] = []  # (class_slug, level, total)
        for cslug, by_lvl in slots.items():
            if isinstance(by_lvl, dict):
                cleaned: dict = {}
                for lvl_key, slot_obj in by_lvl.items():
                    if isinstance(slot_obj, dict):
                        cleaned[lvl_key] = {**slot_obj, "used": 0}
                        try:
                            total = int(slot_obj.get("total") or 0)
                        except (TypeError, ValueError):
                            total = 0
                        if total > 0:
                            try:
                                broadcasts.append((cslug, int(lvl_key), total))
                            except (TypeError, ValueError):
                                pass
                    else:
                        cleaned[lvl_key] = slot_obj
                new_slots[cslug] = cleaned
            else:
                new_slots[cslug] = by_lvl
        sheet["spell_slots"] = new_slots
        sheet["hp"] = hp
        sheet["hit_dice"] = hd
        char.sheet = sheet
        # Long rest restores HP to max and clears any dying/stable state.
        # Route through the death-save state machine so the broadcast +
        # tracker UI stay in sync.
        hp_result = _apply_hp_change(char, long_rest_new_cur)
        db.commit()
        if hp_result["status_changed"]:
            await hub.broadcast(campaign_id, {
                "type": "character_death_save",
                "data": {
                    "character_id": char.id,
                    "status": hp_result["death_saves"]["status"],
                    "successes": int(hp_result["death_saves"]["successes"]),
                    "failures": int(hp_result["death_saves"]["failures"]),
                    "hp": hp_result["hp"],
                    "source": "long_rest",
                },
            })

        # Broadcast slot-pip updates so any open sheet / mini-sheet re-renders
        for cslug, lvl, total in broadcasts:
            try:
                await hub.broadcast(campaign_id, {
                    "type": "spell_slot_update",
                    "data": {
                        "character_id": char.id,
                        "class_slug": cslug,
                        "level": lvl,
                        "total": total,
                        "used": 0,
                    },
                })
            except Exception:
                pass

        # Broadcast resource refills for any open Class Resources panel
        for r in refilled_resources:
            try:
                await hub.broadcast(campaign_id, {
                    "type": "resource_update",
                    "data": {
                        "character_id": char.id,
                        "key": r.get("key"),
                        "current": int(r.get("current") or 0),
                        "max": int(r.get("max") or 0),
                    },
                })
            except Exception:
                pass

        return {"ok": True, "type": "long", "hp": hp_result["hp"], "hit_dice": hd, "resources": refilled_resources}

    # Short rest
    if hd_cur <= 0:
        return JSONResponse(
            status_code=409, content={"error": "no_hit_dice", "hit_dice": hd}
        )

    import re as _re
    die_str = (sheet.get("class_hit_die") or "").strip() or "d8"
    m = _re.search(r"d(\d+)", die_str, _re.IGNORECASE)
    die_size = int(m.group(1)) if m else 8

    abilities = sheet.get("abilities") or {}
    con_score = int(abilities.get("CON") or 10)
    con_mod = (con_score - 10) // 2

    sign = "+" if con_mod >= 0 else ""
    expr = f"1d{die_size}{sign}{con_mod}" if con_mod != 0 else f"1d{die_size}"
    try:
        result = dice_mod.roll(expr)
        recovered = max(1, result.total)
        breakdown = result.breakdown
    except dice_mod.DiceParseError:
        recovered = 1
        breakdown = ""

    new_hp = min(hp_max, hp_cur + recovered) if hp_max > 0 else (hp_cur + recovered)
    hd["current"] = hd_cur - 1
    hd["max"] = hd_max
    sheet["hp"] = hp
    sheet["hit_dice"] = hd
    char.sheet = sheet
    # Short rest healing goes through the state machine so a dying
    # character who somehow ends up able to take a short rest (e.g. via
    # the GM rolling them stable then back up) cleanly wakes them.
    hp_result = _apply_hp_change(char, new_hp)
    db.commit()
    if hp_result["status_changed"]:
        await hub.broadcast(campaign_id, {
            "type": "character_death_save",
            "data": {
                "character_id": char.id,
                "status": hp_result["death_saves"]["status"],
                "successes": int(hp_result["death_saves"]["successes"]),
                "failures": int(hp_result["death_saves"]["failures"]),
                "hp": hp_result["hp"],
                "source": "short_rest",
            },
        })

    # Broadcast resource refills for any short-rest resources (Action Surge,
    # Channel Divinity, Ki, Superiority Dice, …) so live panels re-pip.
    for r in refilled_resources:
        try:
            await hub.broadcast(campaign_id, {
                "type": "resource_update",
                "data": {
                    "character_id": char.id,
                    "key": r.get("key"),
                    "current": int(r.get("current") or 0),
                    "max": int(r.get("max") or 0),
                },
            })
        except Exception:
            pass

    return {
        "ok": True,
        "type": "short",
        "hp": hp_result["hp"],
        "hit_dice": hd,
        "expression": expr,
        "recovered": recovered,
        "breakdown": breakdown,
        "resources": refilled_resources,
    }


# ----------- API: class / subclass resource use -----------

@router.post("/api/campaign/{campaign_id}/character/{char_id}/resource")
async def use_resource(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Spend or restore a trackable class/subclass resource.

    Body:
        {"key": "<resource key>", "delta": -1}     # spend (negative)
        {"key": "<resource key>", "delta": +1}     # restore by N
        {"key": "<resource key>", "set": N}        # set current absolute
        {"key": "<resource key>", "reset": true}   # refill to max

    Returns 409 ``{"error": "no_uses", ...}`` when a spend would go below 0
    so the caller can show a non-blocking toast instead of mutating state.

    Broadcasts a ``resource_update`` WS message so other connected clients
    (mini-sheet, popped-out roll log) can re-render the pip count.
    """
    body = await request.json()
    key = str(body.get("key") or "").strip()
    if not key:
        raise HTTPException(400, "key is required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    if char.template == "dnd5e":
        normalize_dnd5e_sheet(sheet)
    resources = list(sheet.get("resources") or [])
    idx = next(
        (i for i, r in enumerate(resources)
         if isinstance(r, dict) and (r.get("key") or "") == key),
        None,
    )
    if idx is None:
        raise HTTPException(404, "Resource not found on this sheet")

    res = dict(resources[idx])
    mx = int(res.get("max") or 0)
    cur = int(res.get("current") or 0)

    if body.get("reset"):
        # Refill to max
        new_cur = mx
        announce = False
    elif body.get("set") is not None:
        try:
            new_cur = int(body.get("set"))
        except (TypeError, ValueError):
            raise HTTPException(400, "'set' must be an integer")
        announce = False
    else:
        try:
            delta = int(body.get("delta", -1))
        except (TypeError, ValueError):
            raise HTTPException(400, "'delta' must be an integer")
        # Chat-only features (max == 0) never have insufficient uses;
        # we just announce on negative delta and keep current at 0.
        if mx <= 0:
            new_cur = 0
            announce = delta < 0
        else:
            new_cur = cur + delta
            if new_cur < 0:
                return JSONResponse(
                    status_code=409,
                    content={
                        "error": "no_uses",
                        "key": key,
                        "name": res.get("name", ""),
                        "current": cur,
                        "max": mx,
                    },
                )
            announce = delta < 0

    # Clamp [0, max] when max > 0
    if mx > 0:
        new_cur = max(0, min(mx, new_cur))
    else:
        new_cur = max(0, new_cur)

    res["current"] = new_cur
    resources[idx] = res
    sheet["resources"] = resources
    char.sheet = sheet
    db.commit()

    await hub.broadcast(campaign_id, {
        "type": "resource_update",
        "data": {
            "character_id": char.id,
            "key": key,
            "current": new_cur,
            "max": mx,
        },
    })

    # If the caller explicitly asks for a chat announcement (or this was a
    # chat-only feature being "used"), drop a note into the roll log so the
    # rest of the table sees that the feature fired.
    note_label = ""
    if announce and (body.get("announce") is not False):
        membership = (
            db.query(CampaignMembership)
            .filter(CampaignMembership.campaign_id == campaign_id,
                    CampaignMembership.user_id == user.id)
            .first()
        )
        player_color = (
            membership.color if membership and membership.color
            else (campaign.gm_color if user.id == campaign.gm_user_id else None)
        )
        caster_color = char.color or player_color
        note_label = res.get("name", "feature")
        await hub.broadcast(campaign_id, {
            "type": "feature_used",
            "data": {
                "character_id": char.id,
                "character_name": char.name,
                "user_color": caster_color,
                "feature_name": note_label,
                "feature_desc": res.get("desc", ""),
                "source": res.get("source", ""),
                "remaining": new_cur,
                "max": mx,
            },
        })

    return {
        "ok": True,
        "key": key,
        "current": new_cur,
        "max": mx,
        "announced": bool(note_label),
    }


# ----------- API: Wild Shape / Polymorph transform -----------

# Wild Shape CR cap by druid level (RAW). Moon Druid escalates faster.
_WS_CR_DEFAULT = [
    (2, 0.25), (4, 0.5), (8, 1.0),   # lv2: 1/4, lv4: 1/2, lv8: 1
]
_WS_CR_MOON = [
    (2, 1.0), (4, 2.0), (6, 3.0), (8, 4.0), (10, 5.0), (12, 6.0),
]

def _ws_cr_cap(druid_level: int, is_moon: bool) -> float:
    """Max CR a druid of the given level can Wild Shape into (RAW)."""
    table = _WS_CR_MOON if is_moon else _WS_CR_DEFAULT
    cap = 0.0
    for lvl, cr in table:
        if druid_level >= lvl:
            cap = cr
    return cap


def _cr_to_float(cr_raw) -> float:
    """Parse '1/4' / '0' / '2' / '1/2' / '' into a float. Returns 0.0 on
    anything unparseable."""
    if cr_raw is None:
        return 0.0
    s = str(cr_raw).strip()
    if not s:
        return 0.0
    if "/" in s:
        try:
            a, b = s.split("/", 1)
            return float(a) / float(b) if float(b) else 0.0
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _fetch_open5e_creature(slug: str) -> dict:
    """Pull a creature stat block from the Open5e v2 API.

    First tries a direct slug lookup (/v2/creatures/{slug}/) which works for
    v2 keys.  If that returns 404 (e.g. a v1-style slug like ``wolf`` passed
    from a Quick Pick preset), converts the slug to a display name and retries
    via a name search so transforms always succeed regardless of slug format.
    """
    import json as _json
    import urllib.request as _urlreq
    import urllib.error as _urlerr
    import urllib.parse as _urlparse

    def _get(url: str) -> dict:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=10) as r:
            return _json.loads(r.read())

    try:
        return _get(f"{_OPEN5E_BASE}/v2/creatures/{slug}/")
    except _urlerr.HTTPError as exc:
        if exc.code != 404:
            raise HTTPException(502, f"Open5e unavailable: {exc}")
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")

    # Direct lookup 404'd — derive a human name from the slug and search.
    # "brown-bear" → "brown bear", "giant-constrictor-snake" → "giant constrictor snake"
    name_guess = slug.replace("-", " ")
    try:
        search_url = (
            f"{_OPEN5E_BASE}/v2/creatures/"
            f"?name__icontains={_urlparse.quote(name_guess)}&limit=10&type__key=beast"
        )
        data = _get(search_url)
        results = data.get("results", [])
        name_lower = name_guess.lower()
        match = next(
            (r for r in results if (r.get("name") or "").lower() == name_lower),
            results[0] if results else None,
        )
        if match:
            key = match.get("key") or match.get("slug") or ""
            if key:
                return _get(f"{_OPEN5E_BASE}/v2/creatures/{key}/")
    except Exception:
        pass

    raise HTTPException(404, f"Creature '{slug}' not found in Open5e")


@router.post("/api/campaign/{campaign_id}/character/{char_id}/transform")
async def transform_character(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Apply a Wild Shape / Polymorph transformation to a character.

    Body:
        {
          "slug":      "wolf",                       # required
          "source":    "wild-shape" | "polymorph",   # required
          "free_pick": false                         # bypass CR cap if True
        }

    On success: snapshots the character's current HP/AC/speed/abilities/
    attacks/skills/saves into ``sheet["prior_form"]``, replaces those
    fields with the beast's stats (Wild Shape: keeps INT/WIS/CHA;
    Polymorph: replaces all six), sets ``sheet["active_form"]``, and
    decrements the ``wild-shape`` resource if ``source == "wild-shape"``.

    Returns 409 if the character is already transformed, or if the beast's
    CR exceeds the cap for this source/level (and ``free_pick`` is false).
    """
    body = await request.json()
    slug = str(body.get("slug") or "").strip()
    source = str(body.get("source") or "wild-shape").strip().lower()
    free_pick = bool(body.get("free_pick"))
    if not slug:
        raise HTTPException(400, "slug is required")
    if source not in ("wild-shape", "polymorph"):
        raise HTTPException(400, "source must be 'wild-shape' or 'polymorph'")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    if char.template == "dnd5e":
        normalize_dnd5e_sheet(sheet)

    if sheet.get("active_form"):
        existing = sheet["active_form"]
        raise HTTPException(409, f"Already transformed into {existing.get('name', 'a form')}. Revert first.")

    # Fetch beast
    monster = _fetch_open5e_creature(slug)
    creature_type = _o5e_str(monster.get("type")).strip().lower()
    creature_name = (monster.get("name") or slug).strip()
    creature_cr = _cr_to_float(_o5e_cr(monster))

    # Source-specific eligibility checks
    if not free_pick:
        if source == "wild-shape":
            if creature_type != "beast":
                raise HTTPException(409, f"Wild Shape only allows beasts (got '{creature_type or 'unknown'}'). Try 'Free pick (homebrew)' to override.")
            # Find druid level on the roster + detect Moon Druid by subclass
            classes = sheet.get("classes") or []
            druid_lv = 0
            is_moon = False
            for c in classes:
                if isinstance(c, dict) and (c.get("class") or "").strip().lower() == "druid":
                    druid_lv = max(druid_lv, int(c.get("level") or 0))
                    sub = (c.get("subclass") or "").strip().lower()
                    if "moon" in sub:
                        is_moon = True
            if druid_lv < 2:
                raise HTTPException(409, "Wild Shape requires Druid level 2+. Use 'Free pick (homebrew)' to override.")
            cap = _ws_cr_cap(druid_lv, is_moon)
            if creature_cr > cap:
                raise HTTPException(
                    409,
                    f"{creature_name} (CR {_o5e_cr(monster)}) exceeds your Wild Shape CR cap of {cap}. "
                    f"Use 'Free pick (homebrew)' to override.",
                )
        else:  # polymorph
            # Polymorph targets the *target*; for a player polymorphing
            # themselves, the cap is character_level / 4 (rounded down).
            char_level = int(sheet.get("level") or 1)
            cap = max(0.0, char_level / 4.0)
            if creature_cr > cap:
                raise HTTPException(
                    409,
                    f"{creature_name} (CR {_o5e_cr(monster)}) exceeds the Polymorph CR cap of {cap} "
                    f"(target level / 4). Use 'Free pick (homebrew)' to override.",
                )
            if creature_type != "beast":
                raise HTTPException(409, f"Polymorph only targets beasts (got '{creature_type or 'unknown'}'). Try 'Free pick (homebrew)' to override.")

    # Build the beast sheet shape (reuses the GM monster importer helper)
    form_sheet = _open5e_to_dnd5e_sheet(monster)

    # Snapshot prior_form
    prior_form = {
        "hp": dict(sheet.get("hp") or {}),
        "ac": sheet.get("ac"),
        "speed": sheet.get("speed"),
        "abilities": dict(sheet.get("abilities") or {}),
        "skills": dict(sheet.get("skills") or {}),
        "saving_throws": dict(sheet.get("saving_throws") or {}),
        "attacks": list(sheet.get("attacks") or []),
        "race": sheet.get("race"),
        "initiative_bonus": sheet.get("initiative_bonus"),
        "proficiency_bonus": sheet.get("proficiency_bonus"),
        # Defenses follow the beast for the duration of the form — RAW
        # for both Wild Shape and Polymorph (beast stats replace the
        # PC's; Wild Shape preserves the PC's INT/WIS/CHA + class
        # features but not defenses). Snapshot the PC's real-form
        # defenses so revert restores them cleanly.
        "damage_resistances":     list(sheet.get("damage_resistances") or []),
        "damage_immunities":      list(sheet.get("damage_immunities") or []),
        "damage_vulnerabilities": list(sheet.get("damage_vulnerabilities") or []),
        "condition_immunities":   list(sheet.get("condition_immunities") or []),
    }

    # Apply beast stats
    new_abilities = dict(sheet.get("abilities") or {})
    if source == "wild-shape":
        # RAW: keep INT/WIS/CHA, swap STR/DEX/CON
        for ab in ("STR", "DEX", "CON"):
            if ab in form_sheet.get("abilities", {}):
                new_abilities[ab] = form_sheet["abilities"][ab]
    else:
        # Polymorph: full replace per RAW
        new_abilities = dict(form_sheet.get("abilities") or new_abilities)

    sheet["abilities"] = new_abilities
    sheet["hp"] = form_sheet.get("hp") or sheet.get("hp")
    sheet["ac"] = form_sheet.get("ac", sheet.get("ac"))
    sheet["speed"] = form_sheet.get("speed", sheet.get("speed"))
    sheet["skills"] = form_sheet.get("skills") or sheet.get("skills")
    sheet["saving_throws"] = form_sheet.get("saving_throws") or sheet.get("saving_throws")
    sheet["attacks"] = form_sheet.get("attacks") or []
    sheet["race"] = f"{creature_name} (transformed)"
    # Replace the PC's defenses with the beast's for the duration of the
    # form. ``_open5e_to_dnd5e_sheet`` already split Open5e's free-text
    # strings into lists for us; just copy them straight in.
    sheet["damage_resistances"]     = list(form_sheet.get("damage_resistances") or [])
    sheet["damage_immunities"]      = list(form_sheet.get("damage_immunities") or [])
    sheet["damage_vulnerabilities"] = list(form_sheet.get("damage_vulnerabilities") or [])
    sheet["condition_immunities"]   = list(form_sheet.get("condition_immunities") or [])
    # Initiative bonus = DEX mod under the new abilities; keep simple
    try:
        dex = int(new_abilities.get("DEX") or 10)
        sheet["initiative_bonus"] = (dex - 10) // 2
    except (TypeError, ValueError):
        pass

    from datetime import datetime as _dt
    sheet["active_form"] = {
        "slug": slug,
        "name": creature_name,
        "source": source,
        "cr": _o5e_cr(monster),
        "creature_type": creature_type,
        "started_at": _dt.now(timezone.utc).isoformat(),
        "form_sheet": form_sheet,   # full snapshot for reference / future re-apply
    }
    sheet["prior_form"] = prior_form

    # Decrement wild-shape resource if applicable
    resource_update = None
    if source == "wild-shape":
        resources = list(sheet.get("resources") or [])
        for i, r in enumerate(resources):
            if isinstance(r, dict) and (r.get("key") or "") == "wild-shape":
                if int(r.get("max") or 0) > 0:
                    new_cur = max(0, int(r.get("current") or 0) - 1)
                    resources[i] = {**r, "current": new_cur}
                    resource_update = {"key": "wild-shape", "current": new_cur, "max": int(r.get("max") or 0)}
                break
        sheet["resources"] = resources

    from sqlalchemy.orm.attributes import flag_modified
    char.sheet = sheet
    flag_modified(char, "sheet")
    db.commit()

    await hub.broadcast(campaign_id, {
        "type": "transform_update",
        "data": {
            "character_id": char.id,
            "active_form": sheet["active_form"],
            "hp": sheet["hp"],
            "ac": sheet["ac"],
            "speed": sheet["speed"],
        },
    })
    if resource_update is not None:
        await hub.broadcast(campaign_id, {
            "type": "resource_update",
            "data": {"character_id": char.id, **resource_update},
        })

    # Announce in the roll log so the table sees the transformation
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color
    icon = "🐺" if source == "wild-shape" else "🦌"
    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": f"{icon} Transformed into {creature_name}",
            "feature_desc": f"CR {_o5e_cr(monster) or '?'} {creature_type or 'creature'}. "
                            f"Form HP {sheet['hp'].get('current')}/{sheet['hp'].get('max')}, AC {sheet['ac']}.",
            "source": "Wild Shape" if source == "wild-shape" else "Polymorph",
            "remaining": 0,
            "max": 0,
        },
    })

    return {"ok": True, "active_form": sheet["active_form"], "sheet": sheet}


@router.post("/api/campaign/{campaign_id}/character/{char_id}/revert")
async def revert_character(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Revert a Wild Shape / Polymorph back to the character's true form.

    Restores ``sheet["prior_form"]`` onto the live sheet and clears
    ``active_form`` / ``prior_form``.

    Tolerant of "stuck" characters: if ``active_form`` is set but
    ``prior_form`` was lost (e.g. cleared by a pre-v0.35.4 sheet save
    that didn't preserve server-managed fields), the endpoint still
    clears ``active_form`` so the player can edit their sheet back to
    normal. The response carries ``stats_restored: false`` so the UI
    can warn that stats need manual fix-up. Returns 409 only when the
    character is genuinely not transformed (no active_form either).

    RAW Wild Shape: damage that drops the form to 0 HP "overflows" to
    the character's real HP. If the caller passes
    ``{"overflow_damage": N}``, that amount is subtracted from the
    restored real-form HP (clamped to 0).
    """
    body = await request.json() if (await request.body()) else {}
    try:
        overflow = max(0, int(body.get("overflow_damage") or 0))
    except (TypeError, ValueError):
        overflow = 0

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    if char.template == "dnd5e":
        normalize_dnd5e_sheet(sheet)

    prior = sheet.get("prior_form")
    active = sheet.get("active_form") or {}

    # Neither set → genuinely not transformed.
    if not isinstance(prior, dict) and not active:
        raise HTTPException(409, "Character is not currently transformed")

    # Rescue path: active_form is set but prior_form was wiped (typically
    # by a save that didn't carry it forward). Clear active_form so the
    # player can edit out of the beast form; warn via stats_restored=False.
    stats_restored = isinstance(prior, dict)

    if stats_restored:
        # Restore prior_form fields onto the live sheet
        for key in ("hp", "ac", "speed", "abilities", "skills", "saving_throws",
                    "attacks", "race", "initiative_bonus", "proficiency_bonus",
                    "damage_resistances", "damage_immunities",
                    "damage_vulnerabilities", "condition_immunities"):
            if key in prior and prior[key] is not None:
                sheet[key] = prior[key]

        # Apply RAW Wild Shape HP overflow: any damage that dropped the
        # form below 0 carries over to the character's real HP.
        if overflow > 0 and isinstance(sheet.get("hp"), dict):
            hp = dict(sheet["hp"])
            hp["current"] = max(0, int(hp.get("current") or 0) - overflow)
            sheet["hp"] = hp

    sheet["active_form"] = None
    sheet["prior_form"] = None

    from sqlalchemy.orm.attributes import flag_modified
    char.sheet = sheet
    flag_modified(char, "sheet")
    db.commit()

    await hub.broadcast(campaign_id, {
        "type": "transform_update",
        "data": {
            "character_id": char.id,
            "active_form": None,
            "hp": sheet.get("hp"),
            "ac": sheet.get("ac"),
            "speed": sheet.get("speed"),
        },
    })

    # Announce the revert in the roll log
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color
    prev_name = active.get("name") or "form"
    note = f"Reverted from {prev_name}"
    if overflow > 0:
        note += f" — {overflow} overflow damage to real HP"
    if not stats_restored:
        note += " — prior stats not restored, please edit manually"
    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": "✨ Reverted to true form",
            "feature_desc": note,
            "source": active.get("source", "transform"),
            "remaining": 0, "max": 0,
        },
    })

    return {"ok": True, "sheet": sheet, "stats_restored": stats_restored}


# ----------- API: weapon / structured attacks -----------

@router.post("/api/campaign/{campaign_id}/attack")
async def use_attack(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Resolve a structured attack from a character's sheet.

    For attack-roll based attacks: rolls 1d20 + attack_bonus AND damage at the
    same time, persists both rolls (so they appear in the roll log if anyone
    pops it out), and broadcasts a single ``weapon_attack`` WS message that
    other clients render as an attack card.

    For save-based attacks (save_dc > 0 and save_ability set): skips the d20
    attack roll and broadcasts a card with a "Prompt save" button instead.
    Damage is still pre-rolled so the GM can decide who takes it.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    attack_index = int(body.get("attack_index", -1))
    if char_id <= 0 or attack_index < 0:
        raise HTTPException(400, "character_id and attack_index are required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    attacks = list(sheet.get("attacks") or [])
    if attack_index >= len(attacks):
        raise HTTPException(404, "Attack not found")
    attack = dict(attacks[attack_index] or {})

    name = (attack.get("name") or "Attack").strip()

    # v2.6.1: Phase 4 over-budget gate. Every weapon attack consumes the
    # action slot (bonus-action attacks are filed under feature/Class
    # abilities, not /attack). See cast_spell for the matching pattern.
    was_used = _is_slot_used(campaign_id, char.id, "action")
    user_is_gm = _user_is_gm(user, campaign, db)
    override = bool(body.get("override"))
    if was_used and not user_is_gm and not override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": "action",
            "char_name": char.name,
            "source": "attack",
            "label": name,
        })
    attack_bonus_raw = str(attack.get("attack_bonus") or "").strip()
    damage_expr_raw = (attack.get("damage") or "").strip()
    damage_type = (attack.get("damage_type") or "").strip()
    range_str = (attack.get("range") or "").strip()
    save_dc = int(attack.get("save_dc") or 0)
    save_ability = (attack.get("save_ability") or "").strip().upper()
    desc = (attack.get("desc") or "").strip()

    is_save = save_dc > 0 and save_ability

    # Build the to-hit expression. Accept "+5", "5", "1d4+3" etc.
    attack_total = None
    attack_breakdown = ""
    attack_roll_state_applied = ""
    if not is_save and attack_bonus_raw:
        bonus_expr = attack_bonus_raw if attack_bonus_raw.startswith(("+", "-"))\
            or any(c.isalpha() for c in attack_bonus_raw)\
            else "+" + attack_bonus_raw
        atk_expr = "1d20" + (bonus_expr if bonus_expr.startswith(("+", "-")) else "+" + bonus_expr)
        # v2.2.0: apply character roll_state to the attack d20.
        atk_expr, attack_roll_state_applied = _apply_roll_state(
            atk_expr, (char.sheet or {}).get("roll_state"),
        )
        try:
            r = dice_mod.roll(atk_expr)
            attack_total = r.total
            attack_breakdown = r.breakdown
        except dice_mod.DiceParseError:
            attack_total = None
            attack_breakdown = ""
    elif not is_save:
        # No bonus given — flat d20
        atk_expr, attack_roll_state_applied = _apply_roll_state(
            "1d20", (char.sheet or {}).get("roll_state"),
        )
        try:
            r = dice_mod.roll(atk_expr)
            attack_total = r.total
            attack_breakdown = r.breakdown
        except dice_mod.DiceParseError:
            attack_total = None
            attack_breakdown = ""

    # Pre-roll damage if a dice expression is provided.
    damage_total = None
    damage_breakdown = ""
    if damage_expr_raw:
        try:
            r = dice_mod.roll(damage_expr_raw)
            damage_total = r.total
            damage_breakdown = r.breakdown
        except dice_mod.DiceParseError:
            damage_total = None
            damage_breakdown = ""

    # Resolve caster display info
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id, CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    attack_id = uuid.uuid4().hex[:12]
    payload = {
        "id": attack_id,
        "caster_user_id": user.id,
        "caster_user_name": user.display_name,
        "caster_user_color": caster_color,
        "caster_portrait_url": char.portrait_url,
        "caster_char_id": char.id,
        "caster_char_name": char.name,
        "attack_index": attack_index,
        "attack_name": name,
        "attack_bonus": attack_bonus_raw,
        "attack_total": attack_total,
        "attack_breakdown": attack_breakdown,
        "damage_expr": damage_expr_raw,
        "damage_type": damage_type,
        "damage_total": damage_total,
        "damage_breakdown": damage_breakdown,
        "range": range_str,
        "save_dc": save_dc if is_save else 0,
        "save_ability": save_ability if is_save else "",
        "desc": desc,
        "is_save": is_save,
        "roll_state_applied": attack_roll_state_applied or None,
        "over_budget": was_used,
        "over_budget_slot": "action" if was_used else "",
    }
    await hub.broadcast(campaign_id, {"type": "weapon_attack", "data": payload})
    # v2.5.5: full-sheet → init chip sync. Weapon attacks always burn the
    # action slot; bonus-action attacks (e.g. off-hand light weapon) come
    # through a separate row whose action.economy override is followed
    # in Phase 3, not here.
    await _mark_battle_economy(campaign_id, char.id, "action")
    # Return the attack + damage totals so the sheet's .atk-strike handler can
    # fire the shared roll-toast immediately. The broadcast still drives the
    # tabletop's roll-card path; this echo gives the rolling player a popup
    # without needing a WebSocket connection on the sheet page.
    return {
        "ok": True,
        "id": attack_id,
        "attack_total": attack_total,
        "attack_breakdown": attack_breakdown,
        "damage_total": damage_total,
        "damage_breakdown": damage_breakdown,
        "attack_name": name,
        "damage_type": damage_type,
        "is_save": is_save,
        "save_ability": save_ability if is_save else "",
        "save_dc": save_dc if is_save else 0,
        "roll_state_applied": attack_roll_state_applied or None,
        "over_budget": was_used,
    }


# ----------- API: Open5e item proxy (weapons / armor / magic items) -----------

@router.get("/api/open5e/items")
def open5e_items_proxy(type: str = "weapons", search: str = "", limit: int = 60):
    """Search Open5e for weapons / armor / magic items.

    Items aren't part of the local Open5e cache, so this always proxies the
    public API. Type is one of "weapons", "armor", "magicitems".
    """
    cat = (type or "weapons").strip().lower()
    if cat not in ("weapons", "armor", "magicitems"):
        raise HTTPException(400, "type must be one of weapons, armor, magicitems")
    cap = max(1, min(int(limit or 60), 200))

    import json as _json
    import urllib.parse as _urlparse
    import urllib.request as _urlreq

    qs = _urlparse.urlencode({"search": search or "", "limit": cap})
    url = f"https://api.open5e.com/v1/{cat}/?{qs}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=10) as r:
            data = _json.loads(r.read())
    except Exception as e:
        raise HTTPException(502, f"Open5e fetch failed: {e}")

    import re as _re
    raw = data.get("results") or []
    items = []
    for it in raw:
        # Open5e v1 armor stores AC in the `armor_class` field as a string
        # like "16" or "11 + Dex modifier (max 2)" or "+2" for shields.
        # Pull the leading integer (ignoring sign) out for `ac` and pass the
        # original string through for the detail panel.
        ac_string = it.get("armor_class") or it.get("ac_string") or it.get("ac_display") or ""
        ac_int = 0
        if ac_string:
            m = _re.search(r"\d+", str(ac_string))
            if m:
                ac_int = int(m.group(0))
        elif it.get("ac_base") or it.get("ac"):
            try:
                ac_int = int(it.get("ac_base") or it.get("ac") or 0)
            except (TypeError, ValueError):
                ac_int = 0

        items.append({
            "slug": it.get("slug") or it.get("key") or "",
            "name": it.get("name") or "",
            "category": it.get("category") or it.get("type") or it.get("rarity") or "",
            "damage_dice": it.get("damage_dice") or "",
            "damage_type": it.get("damage_type") or "",
            "properties": ", ".join(it.get("properties") or []) if isinstance(it.get("properties"), list) else (it.get("properties") or ""),
            "range": it.get("range") or "",
            "ac": ac_int,
            "ac_string": ac_string,
            "armor_type": it.get("category") or "",
            "stealth_disadvantage": bool(it.get("stealth_disadvantage")),
            "strength_requirement": it.get("strength") or "",
            "weight": it.get("weight") or "",
            "cost": it.get("cost") or "",
            "rarity": it.get("rarity") or "",
            "desc": it.get("desc") or it.get("description") or "",
        })
    return {"results": items}


# ----------- API: concentration tracking -----------

@router.post("/api/campaign/{campaign_id}/concentration")
async def set_concentration(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Set (or replace) the concentration effect for a character.
    Allowed by the character's owner or any GM.
    Body: {character_id, spell_name, rounds, notes}
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    body = await request.json()
    char_id = int(body.get("character_id", 0))
    spell_name = str(body.get("spell_name", "")).strip()[:120]
    if not spell_name:
        raise HTTPException(400, "spell_name is required")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")

    is_gm = _user_is_gm(user, campaign, db)
    if not is_gm and char.owner_user_id != user.id:
        raise HTTPException(403, "Not your character")

    rounds_raw = body.get("rounds")
    rounds = int(rounds_raw) if rounds_raw is not None and str(rounds_raw).strip() else None
    notes = str(body.get("notes", "") or "").strip()[:200] or None

    eff = db.query(ConcentrationEffect).filter(
        ConcentrationEffect.campaign_id == campaign_id,
        ConcentrationEffect.character_id == char_id,
    ).first()
    if eff:
        eff.spell_name = spell_name
        eff.rounds_remaining = rounds
        eff.notes = notes
    else:
        eff = ConcentrationEffect(
            campaign_id=campaign_id,
            character_id=char_id,
            spell_name=spell_name,
            rounds_remaining=rounds,
            notes=notes,
        )
        db.add(eff)
    db.commit()

    await hub.broadcast(campaign_id, {
        "type": "concentration_update",
        "data": {
            "character_id": char_id,
            "spell_name": spell_name,
            "rounds_remaining": rounds,
            "notes": notes or "",
            "ended": False,
        },
    })
    return {"ok": True}


@router.delete("/api/campaign/{campaign_id}/concentration/{char_id}")
async def end_concentration(
    campaign_id: int,
    char_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """End the concentration effect for a character."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")

    is_gm = _user_is_gm(user, campaign, db)
    if not is_gm and char.owner_user_id != user.id:
        raise HTTPException(403, "Not your character")

    eff = db.query(ConcentrationEffect).filter(
        ConcentrationEffect.campaign_id == campaign_id,
        ConcentrationEffect.character_id == char_id,
    ).first()
    if eff:
        db.delete(eff)
        db.commit()

    await hub.broadcast(campaign_id, {
        "type": "concentration_update",
        "data": {"character_id": char_id, "ended": True},
    })
    return {"ok": True}


@router.post("/api/campaign/{campaign_id}/concentration/{char_id}/tick")
async def tick_concentration(
    campaign_id: int,
    char_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Decrement rounds_remaining by 1 at the end of the character's turn.
    If rounds_remaining reaches 0, concentration ends automatically.
    Called by the GM's battle tracker when advancing turns.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")

    eff = db.query(ConcentrationEffect).filter(
        ConcentrationEffect.campaign_id == campaign_id,
        ConcentrationEffect.character_id == char_id,
    ).first()
    if not eff:
        return {"ok": True, "active": False}

    # Only decrement if rounds are being tracked
    if eff.rounds_remaining is not None:
        eff.rounds_remaining = max(0, eff.rounds_remaining - 1)
        if eff.rounds_remaining == 0:
            db.delete(eff)
            db.commit()
            await hub.broadcast(campaign_id, {
                "type": "concentration_update",
                "data": {"character_id": char_id, "ended": True, "reason": "expired"},
            })
            return {"ok": True, "active": False, "ended": True}
        db.commit()

    await hub.broadcast(campaign_id, {
        "type": "concentration_update",
        "data": {
            "character_id": char_id,
            "spell_name": eff.spell_name,
            "rounds_remaining": eff.rounds_remaining,
            "notes": eff.notes or "",
            "ended": False,
        },
    })
    return {"ok": True, "active": True, "rounds_remaining": eff.rounds_remaining}


# ----------- API: battle / initiative tracker -----------

@router.put("/api/campaign/{campaign_id}/battle")
async def update_battle(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    state = await request.json()
    hub.set_battle(campaign_id, state)
    await hub.broadcast(campaign_id, {"type": "battle_update", "data": state})
    return {"ok": True}


# ----------- API: character portrait -----------

_PORTRAIT_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads" / "portraits"
_PORTRAIT_DIR.mkdir(parents=True, exist_ok=True)
_MAX_PORTRAIT_BYTES = 5 * 1024 * 1024
_ALLOWED_PORTRAIT_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@router.post("/campaign/{campaign_id}/character/{char_id}/portrait")
async def upload_portrait(
    campaign_id: int,
    char_id: int,
    portrait: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Cannot edit this character")
    ext = Path(portrait.filename or "").suffix.lower() or ".png"
    if ext not in _ALLOWED_PORTRAIT_EXT:
        raise HTTPException(400, "Unsupported image format (use png/jpg/webp/gif)")
    data = await portrait.read()
    if len(data) > _MAX_PORTRAIT_BYTES:
        raise HTTPException(400, "Image exceeds 5 MB limit")
    if char.portrait_url and char.portrait_url.startswith("/static/uploads/portraits/"):
        old_path = Path(__file__).resolve().parent.parent / "static" / char.portrait_url.removeprefix("/static/")
        try:
            old_path.unlink(missing_ok=True)
        except Exception:
            pass
    fname = f"{uuid.uuid4().hex}{ext}"
    (_PORTRAIT_DIR / fname).write_bytes(data)
    char.portrait_url = f"/static/uploads/portraits/{fname}"
    db.commit()
    return {"ok": True, "portrait_url": char.portrait_url}


# ----------- API: token templates -----------

_TMPL_IMG_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads" / "token_templates"
_TMPL_IMG_DIR.mkdir(parents=True, exist_ok=True)


def _tmpl_dict(tmpl: "TokenTemplate") -> dict:
    return {
        "id": tmpl.id,
        "name": tmpl.name,
        "image_url": tmpl.image_url,
        "tags": tmpl.tags or [],
        "template": tmpl.template,
        "sheet": tmpl.sheet or {},
    }


@router.get("/api/campaign/{campaign_id}/templates")
def list_templates(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    tmpls = db.query(TokenTemplate).filter(TokenTemplate.campaign_id == campaign_id).order_by(TokenTemplate.name).all()
    return [_tmpl_dict(t) for t in tmpls]


@router.post("/api/campaign/{campaign_id}/templates")
async def create_template(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    body = await request.json()
    tmpl = TokenTemplate(
        campaign_id=campaign_id,
        name=str(body.get("name", "Unnamed"))[:200],
        tags=body.get("tags", []),
        template=body.get("template", "generic"),
        sheet=body.get("sheet", {}),
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return _tmpl_dict(tmpl)


@router.get("/api/campaign/{campaign_id}/templates/export")
def export_templates(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    tmpls = db.query(TokenTemplate).filter(TokenTemplate.campaign_id == campaign_id).order_by(TokenTemplate.name).all()
    return {"version": 1, "campaign": campaign.name, "templates": [_tmpl_dict(t) for t in tmpls]}


@router.post("/api/campaign/{campaign_id}/templates/import")
async def import_templates(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    body = await request.json()
    raw_list = body if isinstance(body, list) else body.get("templates", [])
    if not isinstance(raw_list, list):
        raise HTTPException(400, "Expected a list of templates")
    created = []
    for td in raw_list[:100]:
        if not isinstance(td, dict):
            continue
        tpl_type = td.get("template", "generic")
        if tpl_type not in ("generic", "dnd5e"):
            tpl_type = "generic"
        tags = td.get("tags", [])
        img = td.get("image_url")
        sheet = td.get("sheet", {})
        t = TokenTemplate(
            campaign_id=campaign_id,
            name=str(td.get("name", "Imported"))[:200],
            image_url=str(img)[:500] if isinstance(img, str) and img else None,
            tags=tags if isinstance(tags, list) else [],
            template=tpl_type,
            sheet=sheet if isinstance(sheet, dict) else {},
        )
        db.add(t)
        db.flush()
        created.append(_tmpl_dict(t))
    db.commit()
    return {"ok": True, "count": len(created), "templates": created}


@router.post("/api/campaign/{campaign_id}/templates/import-monster")
async def import_open5e_monster(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    body = await request.json()
    slug = str(body.get("slug", "")).strip()
    if not slug:
        raise HTTPException(400, "slug required")
    import json as _json
    import urllib.request as _urlreq
    try:
        req = _urlreq.Request(
            f"{_OPEN5E_BASE}/v2/creatures/{slug}/",
            headers={"User-Agent": "SimpleVTT/1.0"},
        )
        with _urlreq.urlopen(req, timeout=10) as r:
            monster = _json.loads(r.read())
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    sheet = _open5e_to_dnd5e_sheet(monster)
    tags = [t for t in [_o5e_str(monster.get("type")), _o5e_str(monster.get("size")), f"CR {_o5e_cr(monster)}"] if t]
    tmpl = TokenTemplate(
        campaign_id=campaign_id,
        name=monster.get("name", slug)[:200],
        tags=tags,
        template="dnd5e",
        sheet=sheet,
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return _tmpl_dict(tmpl)


@router.get("/api/user/gm-campaigns")
def user_gm_campaigns(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    primary = db.query(Campaign).filter(Campaign.gm_user_id == user.id).all()
    co_ids = [
        m.campaign_id
        for m in db.query(CampaignMembership).filter(
            CampaignMembership.user_id == user.id,
            CampaignMembership.is_gm == True,  # noqa: E712
        ).all()
    ]
    co_gm = db.query(Campaign).filter(Campaign.id.in_(co_ids)).all() if co_ids else []
    seen = {c.id for c in primary}
    return [{"id": c.id, "name": c.name} for c in primary + [c for c in co_gm if c.id not in seen]]


def _custom_monster_lite(row: dict) -> dict:
    """Return a file-based homebrew monster record in the same lite shape the
    beast picker receives from Open5e v2 (after normalisation). v2.0.0: the
    input is now a local_content dict (not a CustomMonster row)."""
    return {
        "slug": row.get("slug"),
        "name": row.get("name"),
        "cr": row.get("challenge_rating") or "0",
        "type": row.get("type") or "",
        "size": row.get("size") or "",
        "hp": row.get("hit_points"),
        "ac": row.get("armor_class"),
        "source": "Custom",
        "is_custom": True,
    }


def _cr_to_float(raw: str) -> float:
    """Convert a CR text ("1/4", "5", "0") to a float for ``cr_max``
    filtering. Unknown forms yield 0."""
    s = (raw or "").strip()
    if "/" in s:
        try:
            a, b = s.split("/", 1)
            return float(a) / float(b)
        except (ValueError, ZeroDivisionError):
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


@router.get("/api/open5e/monsters")
def open5e_monsters_proxy(
    search: str = "",
    limit: int = 20,
    type_filter: str = "",
    cr_max: str = "",
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Proxy for the Open5e v2 creatures endpoint.

    Query params:
        search      — text match on creature name (passed through).
        limit       — page size, capped at 50.
        type_filter — when non-empty, narrows to one creature type
                      (e.g. ``beast``). Forwarded to v2 as
                      ``type__key={type_filter}``.
        cr_max      — when non-empty, narrows to creatures of CR <= the
                      given value. Accepts ``"1/4"`` etc.; converted to
                      a decimal and passed as ``cr__lte=``.

    The v2 endpoint uses different field names than v1 (``cr`` rather
    than ``challenge_rating``, ``type`` / ``size`` as ``{key,name}``
    dicts). Output is normalized so the client can rely on the legacy
    flat-string shape regardless of upstream version.

    On a 4xx from v2 (e.g. a filter param the API doesn't accept), we
    retry once without the filter so the picker stays usable.
    """
    import json as _json
    import urllib.parse as _urlparse
    import urllib.request as _urlreq
    import urllib.error as _urlerr

    # ── Campaign-scoped homebrew monsters prepend the list ───────────────
    # Apply the same filters the client wanted upstream (type, cr_max,
    # search) so a homebrew "Awakened Boulder" only shows up when the
    # picker is in beast / Free pick mode.
    custom_rows: list[dict] = []
    custom_slugs: set[str] = set()
    if campaign_id:
        records, _ = local_content.search(
            type="monsters", campaign_id=campaign_id, q=search, limit=min(abs(limit), 50),
        )
        rows = [r for r in records if r.get("_source") == "local-homebrew"]
        if type_filter:
            tf = type_filter.strip().lower()
            rows = [r for r in rows if (r.get("type") or "").lower() == tf]
        if cr_max:
            cap = _cr_to_float(cr_max)
            rows = [r for r in rows if _cr_to_float(r.get("challenge_rating") or "0") <= cap]
        for r in rows:
            custom_rows.append(_custom_monster_lite(r))
            slug_v = r.get("slug")
            if slug_v:
                custom_slugs.add(slug_v)

    def _build_url(use_filters: bool) -> str:
        # Open5e v2 is django-filter based and silently ignores DRF's
        # ``?search=`` — name matching uses ``?name__icontains=foo``
        # instead. The v1 endpoints (still used by the spell / class
        # proxies elsewhere in this file) DO honour ``?search=``, so
        # keep that pattern there but send the v2 idiom here.
        params: dict[str, str] = {
            "limit": str(min(abs(limit), 50)),
        }
        if search:
            params["name__icontains"] = search
        if use_filters and type_filter:
            params["type__key"] = type_filter.strip().lower()
        if use_filters and cr_max:
            try:
                raw = cr_max.strip()
                cr_val = (float(raw.split("/")[0]) / float(raw.split("/")[1])) if "/" in raw else float(raw)
                params["cr__lte"] = str(cr_val)
            except (TypeError, ValueError):
                pass
        return f"{_OPEN5E_BASE}/v2/creatures/?{_urlparse.urlencode(params)}"

    def _fetch(url: str) -> dict:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            return _json.loads(r.read())

    data: dict
    try:
        data = _fetch(_build_url(use_filters=True))
    except _urlerr.HTTPError as exc:
        if 400 <= exc.code < 500:
            # Filter param the API doesn't accept (or schema drift) —
            # retry once with the plain search so the picker still works.
            try:
                data = _fetch(_build_url(use_filters=False))
            except Exception as exc2:
                # If we have homebrew, prefer returning just that over a 502.
                if custom_rows:
                    return {"count": len(custom_rows), "results": custom_rows}
                raise HTTPException(502, f"Open5e unavailable: {exc2}")
        else:
            if custom_rows:
                return {"count": len(custom_rows), "results": custom_rows}
            raise HTTPException(502, f"Open5e unavailable: {exc}")
    except Exception as exc:
        if custom_rows:
            return {"count": len(custom_rows), "results": custom_rows}
        raise HTTPException(502, f"Open5e unavailable: {exc}")

    results = []
    for m in data.get("results", []):
        slug = m.get("key", m.get("slug", ""))
        # Homebrew with the same slug shadows the Open5e entry.
        if slug in custom_slugs:
            continue
        ac = m.get("armor_class", 10)
        if isinstance(ac, list) and ac:
            ac = ac[0].get("value", 10) if isinstance(ac[0], dict) else ac[0]
        results.append({
            "slug": slug,
            "name": m.get("name", ""),
            # v2 uses ``cr`` (string); v1 used ``challenge_rating``. _o5e_cr
            # handles both.
            "cr": _o5e_cr(m),
            # ``type`` / ``size`` arrive as either plain strings (v1) or
            # ``{"key", "name"}`` dicts (v2) — coerce to a string so the
            # client's ``.toLowerCase()`` filter doesn't blow up.
            "type": _o5e_str(m.get("type")),
            "size": _o5e_str(m.get("size")),
            "hp": m.get("hit_points", 0),
            "ac": ac,
            "source": m.get("document__title", m.get("document", {}).get("title", "") if isinstance(m.get("document"), dict) else ""),
        })
    return {
        "count": len(custom_rows) + data.get("count", 0),
        "results": custom_rows + results,
    }


def _creature_lite(m: dict) -> dict:
    """Slim an Open5e creature record down to the same shape returned by
    the monsters list proxy. Used by ``/api/open5e/creature/{slug}`` so
    the picker's Favorites section can render rows that look identical
    to the search results."""
    ac = m.get("armor_class", 10)
    if isinstance(ac, list) and ac:
        ac = ac[0].get("value", 10) if isinstance(ac[0], dict) else ac[0]
    return {
        "slug": m.get("key", m.get("slug", "")),
        "name": m.get("name", ""),
        "cr": _o5e_cr(m),
        "type": _o5e_str(m.get("type")),
        "size": _o5e_str(m.get("size")),
        "hp": m.get("hit_points", 0),
        "ac": ac,
        "source": m.get("document__title", m.get("document", {}).get("title", "") if isinstance(m.get("document"), dict) else ""),
    }


def _creature_full(m: dict) -> dict:
    """Extended creature shape that adds abilities, actions, and speed
    to the lite shape. Used by the beast picker detail panel."""
    base = _creature_lite(m)
    abilities = {}
    for short, full_key in [
        ("STR", "strength"), ("DEX", "dexterity"), ("CON", "constitution"),
        ("INT", "intelligence"), ("WIS", "wisdom"), ("CHA", "charisma"),
    ]:
        val = _o5e_ability(m, short.lower(), full_key)
        abilities[short] = val if val is not None else 10
    actions = []
    for a in (m.get("actions") or []):
        if isinstance(a, dict):
            name = (a.get("name") or "").strip()
            desc = (a.get("desc") or "").strip()
            if name or desc:
                actions.append({"name": name, "desc": desc})
    speed_raw = m.get("speed", {})
    speed = {}
    if isinstance(speed_raw, dict):
        for k, v in speed_raw.items():
            if v:
                speed[k] = v
    return {**base, "abilities": abilities, "actions": actions, "speed": speed}


@router.get("/api/open5e/creature/{slug}")
def open5e_creature_detail(
    slug: str,
    campaign_id: int | None = None,
    full: bool = False,
    db: Session = Depends(get_db),
):
    """Creature lookup by slug.

    When ``full=true``, the response also includes ability scores, actions,
    and speed — used by the beast picker detail panel.

    When ``campaign_id`` is supplied, a homebrew monster with this slug
    in that campaign takes precedence over the Open5e fetch.
    Returns 404 when neither source has the slug.
    """
    slug = (slug or "").strip()
    if not slug:
        raise HTTPException(400, "slug required")
    # 1. Campaign homebrew first (v2.0.0: file-based).
    if campaign_id:
        hit = local_content.resolve(slug.lower(), type="monsters", campaign_id=campaign_id)
        if hit and hit[1] == "local-homebrew":
            return _custom_monster_lite(hit[0])
    # 2. Live Open5e v2.
    import json as _json
    import urllib.request as _urlreq
    import urllib.error as _urlerr
    try:
        req = _urlreq.Request(
            f"{_OPEN5E_BASE}/v2/creatures/{slug}/",
            headers={"User-Agent": "SimpleVTT/1.0"},
        )
        with _urlreq.urlopen(req, timeout=8) as r:
            monster = _json.loads(r.read())
    except _urlerr.HTTPError as exc:
        if exc.code == 404:
            raise HTTPException(404, f"Creature '{slug}' not found")
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    return _creature_full(monster) if full else _creature_lite(monster)


@router.get("/api/open5e/update-check")
def open5e_update_check(request: Request, db: Session = Depends(get_db)):
    """Compare local Open5e data counts against the live public API.

    Only meaningful when LOCAL_OPEN5E=true. Restricted to authenticated users
    so random visitors can't trigger outbound HTTP calls.
    """
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(401, "Login required")
    from ..open5e_local import check_staleness
    return check_staleness()


def _fmt_hit_die(c: dict) -> str:
    hd = c.get("hit_die") or c.get("hit_dice") or ""
    if not hd:
        return ""
    s = str(hd).strip()
    if not s or s == "0":
        return ""
    if s.startswith("1d"):
        return s[1:]   # "1d6" → "d6"
    if s.startswith("d"):
        return s
    try:
        int(s)
        return f"d{s}"
    except ValueError:
        return s


def _class_detail_response(c: dict) -> dict:
    from ..open5e_local import format_class_text
    return {
        "text": format_class_text(c),
        "hit_die": _fmt_hit_die(c),
        "armor": c.get("prof_armor", "") or "",
        "weapons": c.get("prof_weapons", "") or "",
        "tools": c.get("prof_tools", "") or "",
        "saving_throws": c.get("prof_saving_throws", "") or "",
        "skills": c.get("prof_skills", "") or "",
        "spellcasting": (c.get("spellcasting_ability", "") or "").upper(),
        "equipment": c.get("equipment", "") or "",
        "features": c.get("features_json", "") or c.get("features", "") or "",
    }


@router.get("/api/open5e/class-detail")
def open5e_class_detail(
    slug: str = "",
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    from ..open5e_local import is_ready, get_class
    from .. import local_features
    if not slug:
        raise HTTPException(400, "slug required")
    # 1. Local-first provider chain. DB-backed homebrew (custom_classes)
    # wins over the shipped FS overrides; both shadow Open5e fallbacks.
    scopes = [f"campaign:{campaign_id}", "global"] if campaign_id else ["global"]
    record, source = local_features.resolve_class(slug, scopes=scopes, db=db)
    if record:
        return {**_class_detail_response(record), "source": source}
    # 2. Local Open5e mirror (LOCAL_OPEN5E=true).
    if is_ready():
        c = get_class(slug)
        if c:
            local_features.record_miss("class", slug, source="open5e_mirror")
            return {**_class_detail_response(c), "source": "open5e_mirror"}
    # 3. Live Open5e fallback.
    import json as _json, urllib.request as _urlreq
    try:
        req = _urlreq.Request(f"https://api.open5e.com/v1/classes/{slug}/",
                              headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            c = _json.loads(r.read())
    except Exception as exc:
        local_features.record_miss("class", slug, source="open5e_unreachable")
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    local_features.record_miss("class", slug, source="open5e_live")
    return {**_class_detail_response(c), "source": "open5e_live"}


def _subclass_response(s: dict) -> dict:
    from ..open5e_local import format_subclass_text, parse_subclass_features
    parsed = parse_subclass_features(s)
    return {
        "text": format_subclass_text(s),
        "name": parsed["name"],
        "flavor": parsed["flavor"],
        "features": parsed["features"],
    }


@router.get("/api/open5e/subclass-detail")
def open5e_subclass_detail(
    slug: str = "",
    class_slug: str = "",
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    from ..open5e_local import is_ready, get_subclass, format_subclass_text
    from .. import local_features
    if not slug:
        raise HTTPException(400, "slug required")
    # Build the scope priority list.  Campaign-scoped homebrew (DB
    # provider) wins over the shipped global SRD content (FS provider).
    # Caller may omit ``campaign_id`` — then only global content is
    # considered, preserving the v0.40.1 contract.
    scopes = [f"campaign:{campaign_id}", "global"] if campaign_id else ["global"]
    # 1. Local-first provider chain.  Files already match the response
    # shape; synthesise the legacy "text" summary if absent.
    record, source = local_features.resolve_subclass(class_slug, slug, scopes=scopes, db=db)
    if record:
        features = record.get("features") or []
        return {
            "text": record.get("text") or format_subclass_text({
                "name": record.get("name", ""),
                "subclass_flavor": record.get("flavor", ""),
                "feature_items": features,
            }),
            "name": record.get("name", ""),
            "flavor": record.get("flavor", ""),
            "features": features,
            "source": source,
        }
    # 2. Local Open5e mirror.
    if is_ready():
        s = get_subclass(slug)
        if s:
            local_features.record_miss("subclass", slug, class_slug=class_slug, source="open5e_mirror")
            return {**_subclass_response(s), "source": "open5e_mirror"}
    import json as _json, urllib.request as _urlreq

    def _req(url: str) -> dict:
        r = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(r, timeout=8) as resp:
            return _json.loads(resp.read())

    # 3. Live Open5e — primary: v1/subclasses/{slug}/
    try:
        s = _req(f"https://api.open5e.com/v1/subclasses/{slug}/")
        local_features.record_miss("subclass", slug, class_slug=class_slug, source="open5e_live")
        return {**_subclass_response(s), "source": "open5e_live"}
    except Exception:
        pass

    # 4. Live Open5e — fallback: archetype inside the parent class detail
    if class_slug:
        try:
            data = _req(f"https://api.open5e.com/v1/classes/{class_slug}/")
            archetypes = data.get("archetypes") or data.get("subclasses") or []
            for a in archetypes:
                if a.get("slug") == slug or a.get("name", "").lower() == slug.replace("-", " "):
                    local_features.record_miss("subclass", slug, class_slug=class_slug, source="open5e_live")
                    return {**_subclass_response(a), "source": "open5e_live"}
        except Exception:
            pass

    local_features.record_miss("subclass", slug, class_slug=class_slug, source="open5e_unreachable")
    return {"text": "", "name": "", "flavor": "", "features": [], "source": "open5e_unreachable"}


@router.get("/api/open5e/race-detail")
def open5e_race_detail(
    slug: str = "",
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    from ..open5e_local import is_ready, get_race, format_race_text, parse_race_traits
    from .. import local_features
    if not slug:
        raise HTTPException(400, "slug required")

    # 1. Local-first provider chain (DB + reserved FS slot).
    scopes = [f"campaign:{campaign_id}", "global"] if campaign_id else ["global"]
    record, source = local_features.resolve_race(slug, scopes=scopes, db=db)
    if record:
        # Synthesise the legacy Open5e fields the renderers expect.
        synth: dict = {
            "name": record.get("name", ""),
            "ability_bonuses": record.get("ability_bonuses") or [],
            "size": record.get("size") or "",
            "speed": record.get("speed") or {"walk": 30},
            "age": record.get("age") or "",
            "alignment": record.get("alignment") or "",
            "languages": record.get("languages") or "",
        }
        flavor = format_race_text({**synth})  # not used — overwritten below
        # Build the structured response using the existing helpers; pass
        # the same fields ``parse_race_traits`` expects, plus a synthetic
        # ``traits`` markdown blob derived from the structured trait list
        # so the parser round-trips.
        traits_list = record.get("traits_list") or []
        traits_blob = "\n\n".join(
            f"### {t.get('name','').strip()}\n{(t.get('desc') or '').strip()}"
            for t in traits_list if isinstance(t, dict) and t.get("name")
        )
        parsed = parse_race_traits({**synth, "traits": traits_blob})
        # If parse_race_traits fell back to a single "Racial Traits" card
        # because no markdown headings were found (which won't happen with
        # our synthesised blob), prefer the structured list directly.
        return {
            "text":   format_race_text({**synth, "traits": traits_blob}),
            "name":   parsed["name"] or record.get("name", ""),
            "flavor": parsed["flavor"],
            "traits": traits_list or parsed["traits"],
            "source": source,
        }

    # 2. Local Open5e mirror.
    if is_ready():
        r_data = get_race(slug)
        if r_data:
            local_features.record_miss("race", slug, source="open5e_mirror")
            parsed = parse_race_traits(r_data)
            return {
                "text":   format_race_text(r_data),
                "name":   parsed["name"],
                "flavor": parsed["flavor"],
                "traits": parsed["traits"],
                "source": "open5e_mirror",
            }

    # 3. Live Open5e fallback.
    import json as _json, urllib.request as _urlreq
    try:
        req = _urlreq.Request(f"https://api.open5e.com/v1/races/{slug}/",
                              headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            r_data = _json.loads(r.read())
    except Exception as exc:
        local_features.record_miss("race", slug, source="open5e_unreachable")
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    local_features.record_miss("race", slug, source="open5e_live")
    parsed = parse_race_traits(r_data)
    return {
        "text":   format_race_text(r_data),
        "name":   parsed["name"],
        "flavor": parsed["flavor"],
        "traits": parsed["traits"],
        "source": "open5e_live",
    }


@router.get("/api/open5e/subclasses")
def open5e_subclasses_proxy(
    search: str = "",
    class_slug: str = "",
    limit: int = 20,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    from ..open5e_local import is_ready, search_subclasses, _source
    cap = min(abs(limit), 100)

    # ── Campaign-scoped homebrew (DB-backed) takes the top of the list ───────
    # and shadows any Open5e / mirror entry with the same slug.  Carries
    # ``is_custom: true`` so the picker can render an authoring affordance.
    custom_results: list[dict] = []
    custom_slugs: set[str] = set()
    if campaign_id:
        # v2.0.0: file-based subclasses. The file's `slug` is the combined
        # `<class>__<sub>` form; we split for the response shape that the
        # picker UI already consumes (it shows `slug` = the bare sub_slug
        # and filters by class_slug separately).
        records, _ = local_content.search(
            type="subclass_features", campaign_id=campaign_id, q=search, limit=cap,
        )
        for rec in records:
            if rec.get("_source") != "local-homebrew":
                continue
            combined = rec.get("slug") or ""
            cls_part, _, sub_part = combined.partition("__")
            if not sub_part:
                sub_part = combined
                cls_part = rec.get("class_slug") or ""
            if class_slug and cls_part != class_slug:
                continue
            if not sub_part:
                continue
            custom_results.append({
                "name": rec.get("name") or sub_part,
                "slug": sub_part,
                "flavor": (rec.get("subclass_flavor") or rec.get("flavor") or "")[:300],
                "source": "Custom",
                "is_custom": True,
            })
            custom_slugs.add(sub_part)

    def _dedupe(results: list[dict]) -> list[dict]:
        return [r for r in results if r.get("slug") not in custom_slugs]

    if is_ready():
        items, total = search_subclasses(q=search, class_slug=class_slug, limit=cap)
        open5e_rows = [
            {"name": s.get("name", ""), "slug": s.get("slug", ""),
             "flavor": s.get("subclass_flavor", ""), "source": _source(s)}
            for s in items
        ]
        open5e_rows = _dedupe(open5e_rows)
        return {
            "count": len(custom_results) + total - (len(items) - len(open5e_rows)),
            "results": custom_results + open5e_rows,
        }
    import json as _json, urllib.parse as _urlparse, urllib.request as _urlreq

    def _req(url: str) -> dict:
        r = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(r, timeout=8) as resp:
            return _json.loads(resp.read())

    def _q_match(name: str) -> bool:
        return not search or search.lower() in name.lower()

    # ── Primary: v1/subclasses/ ───────────────────────────────────────────────
    try:
        params: dict = {"limit": cap}
        if search:     params["search"] = search
        if class_slug: params["class_slug"] = class_slug
        data = _req(f"https://api.open5e.com/v1/subclasses/?{_urlparse.urlencode(params)}")
        results = []
        for s in data.get("results", []):
            src = s.get("document__title", "") or (
                s.get("document", {}).get("title", "") if isinstance(s.get("document"), dict) else ""
            )
            results.append({"name": s.get("name", ""), "slug": s.get("slug", ""),
                             "flavor": s.get("subclass_flavor", ""), "source": src})
        results = _dedupe(results)
        return {
            "count": len(custom_results) + data.get("count", 0),
            "results": custom_results + results,
        }
    except Exception:
        pass

    # ── Fallback: extract archetypes from the class detail endpoint ───────────
    # The v1/subclasses/ endpoint is unreliable; v1/classes/{slug}/ embeds
    # archetype data (subclasses) directly in the class object.
    if class_slug:
        try:
            data = _req(f"https://api.open5e.com/v1/classes/{class_slug}/")
            archetypes = data.get("archetypes") or data.get("subclasses") or []
            results = []
            for a in archetypes:
                name = a.get("name", "")
                if not _q_match(name):
                    continue
                results.append({
                    "name": name,
                    "slug": a.get("slug", ""),
                    "flavor": a.get("subtypes_name", "") or "",
                    "source": a.get("document__title", ""),
                })
            results = _dedupe(results)
            return {
                "count": len(custom_results) + len(results),
                "results": (custom_results + results)[:cap],
            }
        except Exception:
            pass

    # ── Both Open5e sources failed — still return any homebrew we found. ─────
    return {"count": len(custom_results), "results": custom_results}


@router.get("/api/open5e/classes")
def open5e_classes_proxy(
    search: str = "",
    limit: int = 20,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    from ..open5e_local import is_ready, search_classes, _source
    from .. import local_features
    cap = min(abs(limit), 30)

    # Campaign-scoped homebrew classes prepend the list and shadow any
    # Open5e/mirror entry with the same slug, mirroring the subclass behavior.
    custom_results: list[dict] = []
    custom_slugs: set[str] = set()
    if campaign_id:
        records, _ = local_content.search(
            q=search or "", type="class_features",
            campaign_id=campaign_id, limit=cap,
        )
        for rec in records:
            if rec.get("_source") != "local-homebrew":
                continue
            slug = rec.get("slug")
            custom_results.append({
                "name": rec.get("name"),
                "slug": slug,
                "hit_die": rec.get("hit_die") or 8,
                "source": "Custom",
                "is_custom": True,
            })
            custom_slugs.add(slug)

    # Shipped FS classes sit between campaign homebrew and Open5e — same
    # arrangement as races. If Open5e is unreachable the picker still
    # lists the SRD baseline; if Open5e is reachable the FS entries
    # dedupe out of its results below (detail endpoint resolves to FS
    # regardless).
    fs_results: list[dict] = []
    fs_slugs: set[str] = set()
    needle = (search or "").strip().lower()
    for entry in local_features.list_local_classes():
        slug = entry.get("slug", "")
        if slug in custom_slugs:
            continue
        name = entry.get("name") or slug
        if needle and needle not in name.lower() and needle not in slug.lower():
            continue
        fs_results.append({
            "name": name,
            "slug": slug,
            "hit_die": entry.get("hit_die") or "",
            "source": "SRD",
        })
        fs_slugs.add(slug)

    def _dedupe(results: list[dict]) -> list[dict]:
        skip = custom_slugs | fs_slugs
        return [r for r in results if r.get("slug") not in skip]

    if is_ready():
        items, total = search_classes(q=search, limit=cap)
        rows = [
            {"name": c.get("name", ""), "slug": c.get("slug", ""),
             "hit_die": c.get("hit_die", ""), "source": _source(c)}
            for c in items
        ]
        rows = _dedupe(rows)
        return {
            "count": len(custom_results) + len(fs_results) + total - (len(items) - len(rows)),
            "results": custom_results + fs_results + rows,
        }
    import json as _json, urllib.parse as _urlparse, urllib.request as _urlreq
    url = f"https://api.open5e.com/v1/classes/?{_urlparse.urlencode({'search': search, 'limit': cap})}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        # Open5e unreachable — fall back to homebrew + shipped FS classes.
        if custom_results or fs_results:
            return {
                "count": len(custom_results) + len(fs_results),
                "results": custom_results + fs_results,
            }
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    results = []
    for c in data.get("results", []):
        src = c.get("document__title", "") or (
            c.get("document", {}).get("title", "") if isinstance(c.get("document"), dict) else ""
        )
        results.append({"name": c.get("name", ""), "slug": c.get("slug", ""),
                         "hit_die": c.get("hit_die", ""), "source": src})
    results = _dedupe(results)
    return {
        "count": len(custom_results) + len(fs_results) + data.get("count", 0),
        "results": custom_results + fs_results + results,
    }


@router.get("/api/open5e/races")
def open5e_races_proxy(
    search: str = "",
    limit: int = 20,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    from ..open5e_local import is_ready, search_races, _source
    from .. import local_features
    cap = min(abs(limit), 30)

    # Campaign-scoped homebrew races prepend the list and shadow any
    # Open5e / mirror entry with the same slug, mirroring how classes and
    # subclasses already behave.
    custom_results: list[dict] = []
    custom_slugs: set[str] = set()
    if campaign_id:
        records, _ = local_content.search(
            type="races", campaign_id=campaign_id, q=search, limit=cap,
        )
        for rec in records:
            if rec.get("_source") != "local-homebrew":
                continue
            slug = rec.get("slug") or ""
            if not slug:
                continue
            custom_results.append({
                "name": rec.get("name") or slug,
                "slug": slug,
                "size": rec.get("size") or "",
                "source": "Custom",
                "is_custom": True,
            })
            custom_slugs.add(slug)

    # Shipped FS races sit between campaign homebrew and Open5e — so if
    # Open5e is unreachable the picker still lists the SRD baseline, and
    # if Open5e is reachable the FS entries dedupe out of its results
    # below (the detail endpoint already resolves to FS regardless).
    fs_results: list[dict] = []
    fs_slugs: set[str] = set()
    needle = (search or "").strip().lower()
    for entry in local_features.list_local_races():
        slug = entry.get("slug", "")
        if slug in custom_slugs:
            continue
        name = entry.get("name") or slug
        if needle and needle not in name.lower() and needle not in slug.lower():
            continue
        fs_results.append({
            "name": name,
            "slug": slug,
            "size": entry.get("size", ""),
            "source": "SRD",
        })
        fs_slugs.add(slug)

    def _dedupe(results: list[dict]) -> list[dict]:
        skip = custom_slugs | fs_slugs
        return [r for r in results if r.get("slug") not in skip]

    if is_ready():
        items, total = search_races(q=search, limit=cap)
        rows = [
            {"name": r.get("name", ""), "slug": r.get("slug", ""),
             "size": r.get("size", ""), "source": _source(r)}
            for r in items
        ]
        rows = _dedupe(rows)
        return {
            "count": len(custom_results) + len(fs_results) + total - (len(items) - len(rows)),
            "results": custom_results + fs_results + rows,
        }
    import json as _json, urllib.parse as _urlparse, urllib.request as _urlreq
    url = f"https://api.open5e.com/v1/races/?{_urlparse.urlencode({'search': search, 'limit': cap})}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        # Open5e unreachable — fall back to homebrew + shipped FS races.
        if custom_results or fs_results:
            return {
                "count": len(custom_results) + len(fs_results),
                "results": custom_results + fs_results,
            }
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    results = []
    for r in data.get("results", []):
        src = r.get("document__title", "") or (
            r.get("document", {}).get("title", "") if isinstance(r.get("document"), dict) else ""
        )
        results.append({"name": r.get("name", ""), "slug": r.get("slug", ""),
                         "size": r.get("size", ""), "source": src})
    results = _dedupe(results)
    return {
        "count": len(custom_results) + len(fs_results) + data.get("count", 0),
        "results": custom_results + fs_results + results,
    }


# ── Backgrounds proxy (with homebrew merge) ─────────────────────────────────
#
# Open5e v1 ships a ``/v1/backgrounds/`` endpoint with name, desc, the four
# proficiency strings, equipment, and feature/feature_desc. We expose two
# routes mirroring the class / subclass pattern: a list endpoint that
# searches by name and a per-slug detail endpoint, both honouring
# ``campaign_id`` to prepend / shadow with homebrew.


@router.get("/api/open5e/backgrounds")
def open5e_backgrounds_proxy(
    search: str = "",
    limit: int = 20,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    cap = min(abs(limit), 50)
    custom_results: list[dict] = []
    custom_slugs: set[str] = set()
    if campaign_id:
        records, _ = local_content.search(
            type="backgrounds", campaign_id=campaign_id, q=search, limit=cap,
        )
        for rec in records:
            if rec.get("_source") != "local-homebrew":
                continue
            slug = rec.get("slug") or ""
            if not slug:
                continue
            custom_results.append({
                "name": rec.get("name") or slug,
                "slug": slug,
                "feature": rec.get("feature_name") or "",
                "source": "Custom",
                "is_custom": True,
            })
            custom_slugs.add(slug)

    def _dedupe(results: list[dict]) -> list[dict]:
        return [r for r in results if r.get("slug") not in custom_slugs]

    import json as _json, urllib.parse as _urlparse, urllib.request as _urlreq
    params: dict = {"limit": cap}
    if search:
        params["search"] = search
    url = f"https://api.open5e.com/v1/backgrounds/?{_urlparse.urlencode(params)}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        # Homebrew-only when Open5e is down.
        if custom_results:
            return {"count": len(custom_results), "results": custom_results}
        raise HTTPException(502, f"Open5e unavailable: {exc}")

    results = []
    for b in data.get("results", []):
        src = b.get("document__title", "") or (
            b.get("document", {}).get("title", "") if isinstance(b.get("document"), dict) else ""
        )
        results.append({
            "name": b.get("name", ""),
            "slug": b.get("slug", ""),
            "feature": b.get("feature", ""),
            "source": src,
        })
    results = _dedupe(results)
    return {
        "count": len(custom_results) + data.get("count", 0),
        "results": custom_results + results,
    }


@router.get("/api/open5e/background/{slug}")
def open5e_background_detail(
    slug: str,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    slug = (slug or "").strip()
    if not slug:
        raise HTTPException(400, "slug required")
    from .. import local_features
    scopes = [f"campaign:{campaign_id}", "global"] if campaign_id else ["global"]
    record, source = local_features.resolve_background(slug, scopes=scopes, db=db)
    if record:
        return {**record, "source": source}
    import json as _json, urllib.request as _urlreq, urllib.error as _urlerr
    try:
        req = _urlreq.Request(
            f"https://api.open5e.com/v1/backgrounds/{slug}/",
            headers={"User-Agent": "SimpleVTT/1.0"},
        )
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except _urlerr.HTTPError as exc:
        if exc.code == 404:
            raise HTTPException(404, f"Background '{slug}' not found")
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    return {
        "slug": data.get("slug", slug),
        "name": data.get("name", ""),
        "desc": data.get("desc", ""),
        "skill_proficiencies": data.get("skill_proficiencies", ""),
        "tool_proficiencies": data.get("tool_proficiencies", ""),
        "languages": data.get("languages", ""),
        "equipment": data.get("equipment", ""),
        "feature": data.get("feature", ""),
        "feature_desc": data.get("feature_desc", ""),
        "source": "open5e_live",
    }


# ── Feats proxy (with homebrew merge) ───────────────────────────────────────


@router.get("/api/open5e/feats")
def open5e_feats_proxy(
    search: str = "",
    limit: int = 20,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    cap = min(abs(limit), 50)
    custom_results: list[dict] = []
    custom_slugs: set[str] = set()
    if campaign_id:
        # v2.0.0: campaign-scoped homebrew lives in the file-based content tier.
        # local_content.search returns dicts whose key set matches the Pydantic
        # Feat model, plus `_source` ("local-homebrew" for files we wrote, or
        # "local-srd" for shipped content). We only count `local-homebrew` here
        # to preserve the "Custom" badge the picker UI uses.
        records, _ = local_content.search(
            type="feats", campaign_id=campaign_id, q=search, limit=cap,
        )
        for rec in records:
            if rec.get("_source") != "local-homebrew":
                continue
            slug = rec.get("slug") or ""
            if not slug:
                continue
            custom_results.append({
                "name": rec.get("name") or slug,
                "slug": slug,
                "prerequisite": rec.get("prerequisite") or "",
                "source": "Custom",
                "is_custom": True,
            })
            custom_slugs.add(slug)

    def _dedupe(results: list[dict]) -> list[dict]:
        return [r for r in results if r.get("slug") not in custom_slugs]

    import json as _json, urllib.parse as _urlparse, urllib.request as _urlreq
    params: dict = {"limit": cap}
    if search:
        params["search"] = search
    url = f"https://api.open5e.com/v1/feats/?{_urlparse.urlencode(params)}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        if custom_results:
            return {"count": len(custom_results), "results": custom_results}
        raise HTTPException(502, f"Open5e unavailable: {exc}")

    results = []
    for f in data.get("results", []):
        src = f.get("document__title", "") or (
            f.get("document", {}).get("title", "") if isinstance(f.get("document"), dict) else ""
        )
        results.append({
            "name": f.get("name", ""),
            "slug": f.get("slug", ""),
            "prerequisite": f.get("prerequisite", ""),
            "source": src,
        })
    results = _dedupe(results)
    return {
        "count": len(custom_results) + data.get("count", 0),
        "results": custom_results + results,
    }


@router.get("/api/open5e/feat/{slug}")
def open5e_feat_detail(
    slug: str,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    slug = (slug or "").strip()
    if not slug:
        raise HTTPException(400, "slug required")
    from .. import local_features
    scopes = [f"campaign:{campaign_id}", "global"] if campaign_id else ["global"]
    record, source = local_features.resolve_feat(slug, scopes=scopes, db=db)
    if record:
        return {**record, "source": source}
    import json as _json, urllib.request as _urlreq, urllib.error as _urlerr
    try:
        req = _urlreq.Request(
            f"https://api.open5e.com/v1/feats/{slug}/",
            headers={"User-Agent": "SimpleVTT/1.0"},
        )
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except _urlerr.HTTPError as exc:
        if exc.code == 404:
            raise HTTPException(404, f"Feat '{slug}' not found")
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    return {
        "slug": data.get("slug", slug),
        "name": data.get("name", ""),
        "prerequisite": data.get("prerequisite", ""),
        "desc": data.get("desc", ""),
        "source": "open5e_live",
    }


@router.get("/api/open5e/spells")
def open5e_spells_proxy(
    search: str = "",
    limit: int = 20,
    spell_list: str = "",
    level: int = -1,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    import re as _re

    def _fmt_spell(s: dict) -> dict:
        desc = s.get("desc", "")
        desc = _re.sub(r"[*_#`]+", "", desc).replace("|", ",").replace("\n", " ").strip()
        dmg_m = _re.search(r"(\d+d\d+(?:\s*[+-]\s*\d+)?)\s+(\w+)\s+damage", desc, _re.IGNORECASE)
        damage = f"{dmg_m.group(1).replace(' ', '')} {dmg_m.group(2).lower()}" if dmg_m else ""
        _save_map = {"strength": "STR", "dexterity": "DEX", "constitution": "CON",
                     "intelligence": "INT", "wisdom": "WIS", "charisma": "CHA"}
        save_m = _re.search(
            r"\b(strength|dexterity|constitution|intelligence|wisdom|charisma)\s+saving\s+throw",
            desc, _re.IGNORECASE)
        save_ability = _save_map.get(save_m.group(1).lower(), "") if save_m else ""

        # Healing detection (only on non-damage spells to avoid Vampiric Touch etc.)
        healing = ""
        aoe_targets = 1
        if not damage:
            heal_m = _re.search(
                r"(?:regain|restore|heal)s?\s+(\d+d\d+(?:\s*[+-]\s*\d+)?)\s+hit\s+points",
                desc, _re.IGNORECASE)
            if not heal_m:
                heal_m = _re.search(r"(\d+d\d+(?:\s*[+-]\s*\d+)?)\s+hit\s+points", desc, _re.IGNORECASE)
            if heal_m:
                healing = heal_m.group(1).replace(" ", "")
                aoe_m = _re.search(
                    r"up\s+to\s+(\d+)\s+(?:creatures?|targets?|willing\s+creatures?)",
                    desc, _re.IGNORECASE)
                aoe_targets = int(aoe_m.group(1)) if aoe_m else 1

        # If the input record already carries a structured `actions` array
        # (i.e. it came from the file-based local_content tier), pass it through
        # so the client renders explicit Action buttons rather than re-deriving
        # them from regex-scraped legacy fields.
        explicit_actions = s.get("actions") or []

        return {
            "slug": s.get("slug", ""),
            "name": s.get("name", ""),
            "level": s.get("level_int", s.get("spell_level", 0)),
            "school": s.get("school", ""),
            "casting_time": s.get("casting_time", ""),
            "range": s.get("range", ""),
            "duration": s.get("duration", ""),
            "components": s.get("components", ""),
            "damage": damage,
            "save_ability": save_ability,
            "healing": healing,
            "aoe_targets": aoe_targets,
            "desc": desc,
            "actions": explicit_actions,
        }

    # ── Local-content tier ──────────────────────────────────────────────────
    # Two-tier resolver: homebrew volume files (per-campaign + global) first,
    # then shipped SRD files. Only if both miss do we fall through to the
    # Open5e mirror / live API below.
    from .. import local_content as _lc
    local_results, _local_total = _lc.search(
        q=search,
        type="spells",
        campaign_id=campaign_id,
        limit=200,  # search broadly; level/spell_list filter below applies
    )
    if local_results:
        items = local_results
        if spell_list:
            sl = spell_list.lower()
            items = [s for s in items
                     if sl in [x.lower() for x in (s.get("spell_lists") or [])]]
        if level >= 0:
            items = [s for s in items
                     if (s.get("level_int") or s.get("spell_level") or 0) == level]
        if items:
            return {"count": len(items), "results": [_fmt_spell(s) for s in items[:min(abs(limit), 100)]]}
        # Local tier loaded records but none matched the class/level filter — fall
        # through to Open5e so the picker isn't artificially empty.

    from ..open5e_local import is_ready, search_spells, get_spells_by_slugs
    cap = min(abs(limit), 100)

    # ── Homebrew-class spell list ────────────────────────────────────────────
    # When the picker filters by class slug AND a campaign is supplied AND
    # that (campaign, slug) names a homebrew class, return the spells from
    # the GM's curated list rather than asking Open5e for "spells whose
    # spell_lists field contains <homebrew slug>" (which would always be
    # empty — Open5e doesn't know about the homebrew).
    if spell_list and campaign_id:
        _hb = local_content.resolve(spell_list.lower(), type="class_features", campaign_id=campaign_id)
        homebrew = _hb[0] if (_hb and _hb[1] == "local-homebrew") else None
        if homebrew:
            curated = homebrew.get("spell_list") or []
            if not curated:
                return {"count": 0, "results": []}
            # Local mirror is preferred — single in-memory lookup.  Without
            # it we'd need N parallel HTTP fetches, which is slow enough to
            # warrant requiring the mirror for homebrew lookups.
            if is_ready():
                spells = get_spells_by_slugs(curated)
            else:
                # Fall back to sequential Open5e fetches with a short
                # timeout each; tolerate individual failures.
                import json as _json, urllib.request as _urlreq
                spells = []
                for slug in curated[:cap * 2]:  # cap to a sane upper bound
                    try:
                        req = _urlreq.Request(
                            f"https://api.open5e.com/v1/spells/{slug}/",
                            headers={"User-Agent": "SimpleVTT/1.0"},
                        )
                        with _urlreq.urlopen(req, timeout=4) as r:
                            spells.append(_json.loads(r.read()))
                    except Exception:
                        continue
            # Apply search + level filters in memory.
            if search:
                q = search.lower()
                spells = [s for s in spells if q in (s.get("name") or "").lower()]
            if level >= 0:
                spells = [
                    s for s in spells
                    if (s.get("level_int") or s.get("spell_level") or 0) == level
                ]
            total = len(spells)
            return {"count": total, "results": [_fmt_spell(s) for s in spells[:cap]]}

    # Try the local mirror first when enabled. If it returns zero results
    # for a class+level filter (e.g. the sync ran before a content drop,
    # or the mirror is incomplete) fall through to the live API instead
    # of silently leaving the picker empty.
    if is_ready():
        items, total = search_spells(q=search, limit=cap, spell_list=spell_list, level=level)
        if total > 0:
            return {"count": total, "results": [_fmt_spell(s) for s in items]}
        # Local returned nothing — log + try live as a fallback.
        log.info(
            "Local Open5e spells returned 0 results (spell_list=%r, level=%r, search=%r); "
            "falling back to live API.",
            spell_list, level, search,
        )
    import json as _json, urllib.parse as _urlparse, urllib.request as _urlreq
    params: dict = {"limit": cap}
    if search:     params["search"]      = search
    if spell_list: params["spell_lists"] = spell_list.lower()  # Open5e v1 param name
    if level >= 0: params["level_int"]   = level               # Open5e v1 integer level field
    url = f"https://api.open5e.com/v1/spells/?{_urlparse.urlencode(params)}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=15) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    return {"count": data.get("count", 0), "results": [_fmt_spell(s) for s in data.get("results", [])]}


@router.get("/api/open5e/conditions")
def open5e_conditions_proxy():
    """Return all D&D 5e conditions (small static list — always fetched in full)."""
    def _fmt(c: dict) -> dict:
        return {"slug": c.get("slug", ""), "name": c.get("name", ""), "desc": c.get("desc", "")}

    from ..open5e_local import is_ready, search_conditions
    if is_ready():
        items, _ = search_conditions(limit=50)
        return {"results": [_fmt(c) for c in items]}

    import json as _json, urllib.request as _urlreq
    try:
        req = _urlreq.Request(
            "https://api.open5e.com/v1/conditions/?limit=50",
            headers={"User-Agent": "SimpleVTT/1.0"},
        )
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    return {"results": [_fmt(c) for c in data.get("results", [])]}


def _o5e_str(v) -> str:
    """Coerce an Open5e v1/v2 attribute to a plain string.

    v2 returns ``type`` and ``size`` (and several other taxonomy-ish
    fields) as ``{"key": "beast", "name": "Beast"}`` objects rather
    than the v1 plain-string form. Anything that calls
    ``.toLowerCase()`` / ``.strip()`` on the raw value crashes on v2
    data. This helper normalizes both shapes to a display string;
    callers downstream can ``.lower()`` / ``.strip()`` it freely.
    """
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return str(v.get("name") or v.get("key") or "")
    return str(v)


def _o5e_cr(m: dict) -> str:
    """Read the challenge rating regardless of v1/v2 shape.

    v2 (creatures endpoint) uses ``cr`` — a string like ``"1/4"`` or
    ``"5"``. v1 uses ``challenge_rating``. Returns the raw string so
    callers can decide whether to render or parse to a float.
    """
    raw = m.get("cr")
    if raw is None or raw == "":
        raw = m.get("challenge_rating")
    if raw is None:
        return "0"
    return str(raw)


def _o5e_ability(m: dict, ability_key: str, full_key: str) -> int | None:
    """Read a single ability score in a way that works for both API versions.

    - v1 puts each score at the top level: ``m["strength"] = 12``.
    - v2 nests them under ``ability_scores``: ``m["ability_scores"]["str"] = 12``.

    Returns the score as an int, or None if not present. Caller decides
    the default.
    """
    nested = m.get("ability_scores")
    if isinstance(nested, dict):
        # Try all known key formats: lowercase short ("str"), uppercase short
        # ("STR"), and full name ("strength") — different Open5e builds vary.
        for candidate in (ability_key, ability_key.upper(), full_key):
            val = nested.get(candidate)
            if val is not None:
                try:
                    return int(val)
                except (TypeError, ValueError):
                    pass
    val = m.get(full_key)
    if val is not None:
        try:
            return int(val)
        except (TypeError, ValueError):
            pass
    return None


def _o5e_save_prof(m: dict, ability_key: str, full_save_key: str) -> bool:
    """True when the creature is proficient with a given saving throw.

    v1 exposes ``strength_save = 4`` (a final bonus, presence implies
    proficiency). v2 nests them under ``saving_throws`` keyed by
    short ability name (``str``, ``dex``, …) with a numeric value when
    proficient.
    """
    nested = m.get("saving_throws")
    if isinstance(nested, dict) and nested.get(ability_key) is not None:
        return True
    return m.get(full_save_key) is not None


def _o5e_skill_prof(m: dict, snake_key: str) -> bool:
    """True when the creature is proficient with a skill.

    v1 surfaces e.g. ``perception = 5`` at the top level. v2 nests
    them under ``skill_bonuses``."""
    nested = m.get("skill_bonuses")
    if isinstance(nested, dict) and nested.get(snake_key) is not None:
        return True
    return m.get(snake_key) is not None


def _open5e_to_dnd5e_sheet(m: dict) -> dict:
    import copy
    import re
    from ..sheet_templates import DND5E_TEMPLATE

    sheet = copy.deepcopy(DND5E_TEMPLATE)

    # HP
    hp = int(m.get("hit_points") or 10)
    sheet["hp"] = {"current": hp, "max": hp, "temp": 0}

    # AC — integer or list of dicts in v2
    ac = m.get("armor_class", 10)
    if isinstance(ac, list) and ac:
        ac = ac[0].get("value", 10) if isinstance(ac[0], dict) else ac[0]
    if isinstance(ac, str):
        digs = re.search(r"\d+", ac)
        ac = int(digs.group()) if digs else 10
    sheet["ac"] = int(ac or 10)

    # Speed — dict {"walk": 30} or string
    speed_raw = m.get("speed", {})
    if isinstance(speed_raw, dict):
        walk = speed_raw.get("walk", 30)
        if isinstance(walk, str):
            digs = re.search(r"\d+", walk)
            walk = int(digs.group()) if digs else 30
        sheet["speed"] = int(walk or 30)
    elif isinstance(speed_raw, (int, float)):
        sheet["speed"] = int(speed_raw)
    else:
        digs = re.search(r"\d+", str(speed_raw))
        sheet["speed"] = int(digs.group()) if digs else 30

    # Ability scores — handle both v1 (top-level) and v2 (nested under
    # ``ability_scores``). v2 uses 3-letter keys (``str``, ``dex``, …);
    # v1 uses the full names.
    for ab, short, full in [
        ("STR", "str", "strength"),
        ("DEX", "dex", "dexterity"),
        ("CON", "con", "constitution"),
        ("INT", "int", "intelligence"),
        ("WIS", "wis", "wisdom"),
        ("CHA", "cha", "charisma"),
    ]:
        val = _o5e_ability(m, short, full)
        if val is not None:
            sheet["abilities"][ab] = val

    # CR → proficiency bonus
    cr_str = _o5e_cr(m)
    try:
        cr_val = float(cr_str.split("/")[0]) / float(cr_str.split("/")[1]) if "/" in cr_str else float(cr_str)
    except Exception:
        cr_val = 0.0
    sheet["proficiency_bonus"] = (
        2 if cr_val < 5 else 3 if cr_val < 9 else 4 if cr_val < 13 else
        5 if cr_val < 17 else 6 if cr_val < 21 else 7 if cr_val < 25 else
        8 if cr_val < 29 else 9
    )

    # Creature meta
    sheet["race"] = f"{_o5e_str(m.get('size'))} {_o5e_str(m.get('type'))}".strip()
    sheet["background"] = _o5e_str(m.get("alignment"))

    # Saving throw proficiencies — v1 has ``strength_save`` etc. at the top
    # level; v2 nests under ``saving_throws.{short}``.
    for ab, short, full in [
        ("STR", "str", "strength_save"),
        ("DEX", "dex", "dexterity_save"),
        ("CON", "con", "constitution_save"),
        ("INT", "int", "intelligence_save"),
        ("WIS", "wis", "wisdom_save"),
        ("CHA", "cha", "charisma_save"),
    ]:
        if _o5e_save_prof(m, short, full):
            sheet["saving_throws"][ab] = True

    # Skill proficiencies — v1 has ``perception`` etc. at top level; v2
    # nests under ``skill_bonuses.<snake>``.
    skill_map = {
        "acrobatics": "Acrobatics", "animal_handling": "Animal Handling", "arcana": "Arcana",
        "athletics": "Athletics", "deception": "Deception", "history": "History",
        "insight": "Insight", "intimidation": "Intimidation", "investigation": "Investigation",
        "medicine": "Medicine", "nature": "Nature", "perception": "Perception",
        "performance": "Performance", "persuasion": "Persuasion", "religion": "Religion",
        "sleight_of_hand": "Sleight of Hand", "stealth": "Stealth", "survival": "Survival",
    }
    for api_key, skill_name in skill_map.items():
        if _o5e_skill_prof(m, api_key) and skill_name in sheet["skills"]:
            sheet["skills"][skill_name]["proficient"] = True

    # Actions → attacks
    attacks = []
    for action in (m.get("actions") or []):
        desc = action.get("desc", "")
        bonus_m = re.search(r"([+-]\d+) to hit", desc)
        dmg_m = re.search(r"(\d+d\d+(?:\s*[+-]\s*\d+)?)\s+\w+\s+damage", desc)
        attacks.append({
            "name": action.get("name", ""),
            "bonus": bonus_m.group(1) if bonus_m else "",
            "damage": dmg_m.group(1).replace(" ", "") if dmg_m else "",
        })
    sheet["attacks"] = attacks

    # Special abilities → features
    features = []
    for sa in (m.get("special_abilities") or []):
        name = sa.get("name", "")
        desc = sa.get("desc", "")
        if name or desc:
            features.append(f"{name}: {desc}" if name else desc)
    sheet["features"] = "\n\n".join(features)

    # Defenses — Open5e returns these as free-text strings (e.g.
    # ``"fire, cold"`` or ``"bludgeoning, piercing, and slashing from
    # nonmagical attacks not made with silvered weapons"``). Split on
    # commas and " and " for the common simple-list cases; anything
    # more complex lands as a single custom chip the player can clean
    # up after transforming. ``normalize_dnd5e_sheet`` later dedupes
    # case-insensitively and caps the lists.
    def _split_defense(raw: object) -> list[str]:
        if not raw:
            return []
        if isinstance(raw, list):
            parts = [str(p) for p in raw]
        else:
            text = str(raw)
            # Replace " and " with comma to merge into a single split below.
            text = re.sub(r"\s+and\s+", ", ", text)
            parts = re.split(r"[,;]", text)
        return [p.strip() for p in parts if p and p.strip()]

    sheet["damage_resistances"]     = _split_defense(m.get("damage_resistances"))
    sheet["damage_immunities"]      = _split_defense(m.get("damage_immunities"))
    sheet["damage_vulnerabilities"] = _split_defense(m.get("damage_vulnerabilities"))
    sheet["condition_immunities"]   = _split_defense(m.get("condition_immunities"))

    # Notes: stat block meta (defenses are now first-class fields above,
    # so we don't dump them into Notes — leaves room for languages /
    # senses / hit dice / CR).
    parts = []
    for label, key in [
        ("Hit Dice", "hit_dice"), ("CR", "challenge_rating"),
        ("Languages", "languages"), ("Senses", "senses"),
    ]:
        if m.get(key):
            parts.append(f"{label}: {m[key]}")
    sheet["notes"] = "\n".join(parts)

    return sheet


@router.patch("/api/campaign/{campaign_id}/templates/{tmpl_id}")
async def update_template(
    campaign_id: int,
    tmpl_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    tmpl = db.query(TokenTemplate).filter(TokenTemplate.id == tmpl_id, TokenTemplate.campaign_id == campaign_id).first()
    if not tmpl:
        raise HTTPException(404, "Template not found")
    body = await request.json()
    if "name" in body:
        tmpl.name = str(body["name"])[:200]
    if "tags" in body:
        tmpl.tags = body["tags"] if isinstance(body["tags"], list) else []
    if "template" in body and body["template"] in ("generic", "dnd5e"):
        tmpl.template = body["template"]
    if "sheet" in body and isinstance(body["sheet"], dict):
        tmpl.sheet = body["sheet"]
    db.commit()
    return _tmpl_dict(tmpl)


@router.delete("/api/campaign/{campaign_id}/templates/{tmpl_id}")
async def delete_template(
    campaign_id: int,
    tmpl_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    tmpl = db.query(TokenTemplate).filter(TokenTemplate.id == tmpl_id, TokenTemplate.campaign_id == campaign_id).first()
    if not tmpl:
        raise HTTPException(404, "Template not found")
    if tmpl.image_url and tmpl.image_url.startswith("/static/uploads/token_templates/"):
        p = Path(__file__).resolve().parent.parent / "static" / tmpl.image_url.removeprefix("/static/")
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
    db.delete(tmpl)
    db.commit()
    return {"ok": True}


@router.post("/api/campaign/{campaign_id}/templates/{tmpl_id}/image")
async def upload_template_image(
    campaign_id: int,
    tmpl_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    tmpl = db.query(TokenTemplate).filter(TokenTemplate.id == tmpl_id, TokenTemplate.campaign_id == campaign_id).first()
    if not tmpl:
        raise HTTPException(404, "Template not found")
    ext = Path(image.filename or "").suffix.lower() or ".png"
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        raise HTTPException(400, "Unsupported image type")
    data = await image.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Image exceeds 5 MB")
    if tmpl.image_url and tmpl.image_url.startswith("/static/uploads/token_templates/"):
        old = Path(__file__).resolve().parent.parent / "static" / tmpl.image_url.removeprefix("/static/")
        try:
            old.unlink(missing_ok=True)
        except Exception:
            pass
    fname = f"{uuid.uuid4().hex}{ext}"
    (_TMPL_IMG_DIR / fname).write_bytes(data)
    tmpl.image_url = f"/static/uploads/token_templates/{fname}"
    db.commit()
    return {"ok": True, "image_url": tmpl.image_url}


@router.get("/api/campaign/{campaign_id}/templates/{tmpl_id}/sheet", response_class=HTMLResponse)
def get_template_sheet(
    campaign_id: int,
    tmpl_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Returns sheet HTML for editing a token template's sheet data."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    tmpl = db.query(TokenTemplate).filter(TokenTemplate.id == tmpl_id, TokenTemplate.campaign_id == campaign_id).first()
    if not tmpl:
        raise HTTPException(404, "Template not found")

    class _Char:
        pass

    char_obj = _Char()
    char_obj.id = tmpl.id
    char_obj.name = tmpl.name
    char_obj.portrait_url = tmpl.image_url
    char_obj.template = tmpl.template

    tname = "sheet_dnd5e.html" if tmpl.template == "dnd5e" else "sheet_generic.html"
    tmpl_sheet = tmpl.sheet or get_template(tmpl.template)
    if tmpl.template == "dnd5e":
        normalize_dnd5e_sheet(tmpl_sheet)
    return templates.TemplateResponse(tname, {
        "request": request,
        "char": char_obj,
        "sheet": tmpl_sheet,
        "can_edit": True,
        "campaign": campaign,
        "sheet_save_url": f"/api/campaign/{campaign_id}/templates/{tmpl_id}",
        "sheet_save_method": "PATCH",
        "portrait_upload_url": f"/api/campaign/{campaign_id}/templates/{tmpl_id}/image",
        "class_roster": class_levels_summary(tmpl_sheet) if tmpl.template == "dnd5e" else [],
        "animate_gifs": user.animate_gifs,
    })


# ----------- API: character sheets -----------

@router.get("/api/campaign/{campaign_id}/character/{char_id}", response_class=HTMLResponse)
def get_sheet(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Forbidden")
    is_gm = _user_is_gm(user, campaign, db)
    can_edit = is_gm or char.owner_user_id == user.id
    template_name = "sheet_dnd5e.html" if char.template == "dnd5e" else "sheet_generic.html"
    sheet = char.sheet or get_template(char.template)
    if char.template == "dnd5e":
        normalize_dnd5e_sheet(sheet)
    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "char": char,
            "sheet": sheet,
            "can_edit": can_edit,
            "is_gm": is_gm,
            "campaign": campaign,
            "class_roster": class_levels_summary(sheet) if char.template == "dnd5e" else [],
            "animate_gifs": user.animate_gifs,
        },
    )


@router.post("/api/campaign/{campaign_id}/character/{char_id}")
async def update_sheet(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    body = await request.json()
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Forbidden")
    if "name" in body:
        char.name = str(body["name"])[:120]
    hp_result = None
    if "sheet" in body and isinstance(body["sheet"], dict):
        incoming = body["sheet"]
        existing = dict(char.sheet or {})
        # Server-managed fields that have no form inputs on the sheet. The
        # client's buildSheet() can't include them in its payload, so a
        # naive replace would strand any transformed character (active_form
        # set, prior_form lost — see bug repro in v0.35.4). Carry these
        # forward from the persisted sheet whenever the client didn't send
        # them explicitly. hp_rolls is in the same category — populated
        # exclusively through the /sheet-fields PATCH from the edit panel
        # picker. ``death_saves`` (v2.1.0) is also server-managed — the
        # full sheet POST shouldn't blow away dying/stable state.
        for k in ("active_form", "prior_form", "hp_rolls", "favorite_beasts",
                  "damage_resistances", "damage_immunities",
                  "damage_vulnerabilities", "condition_immunities",
                  "death_saves", "roll_state"):
            if k in existing and k not in incoming:
                incoming[k] = existing[k]
        # Detect HP transitions so the state machine fires on full sheet save.
        old_current = int((existing.get("hp") or {}).get("current") or 0)
        new_current = int((incoming.get("hp") or {}).get("current") or 0)
        char.sheet = incoming
        if old_current != new_current:
            hp_result = _apply_hp_change(char, new_current)
    if "template" in body and body["template"] in ("generic", "dnd5e"):
        char.template = body["template"]
    db.commit()
    await hub.broadcast(
        campaign_id,
        {"type": "character_update", "data": {"id": char.id, "name": char.name}},
    )
    if hp_result and hp_result["status_changed"]:
        await hub.broadcast(campaign_id, {
            "type": "character_death_save",
            "data": {
                "character_id": char.id,
                "status": hp_result["death_saves"]["status"],
                "successes": int(hp_result["death_saves"]["successes"]),
                "failures": int(hp_result["death_saves"]["failures"]),
                "hp": hp_result["hp"],
                "source": "full_save",
            },
        })
    return {"ok": True}


# Allowed keys for the lightweight sheet-fields patch (avoids full-sheet replace).
# subclass_features_data kept for backward-compat; the three individual keys let
# each feature be stored and queried without re-parsing the whole blob.
_SHEET_PATCH_KEYS = {
    # HP object {current, max, temp}
    "hp",
    # Subclass features (new per-feature format + legacy blob)
    "subclass_features_data",   # legacy blob (kept for backwards compat)
    "subclass_name",
    "subclass_flavor",
    "subclass_features",        # list[{name, desc, level}]
    # Race traits (same pattern)
    "race_parsed_data",         # legacy blob
    "race_flavor",
    "race_trait_items",         # list[{name, desc}]
    # Full spells list — used by the Subclass Spells / Feature Grants panels
    # to persist a player's granted-spell pick the moment they choose one,
    # so the dropdown's selection survives a refresh without an explicit Save.
    "spells",
    # Per-class subclass-variant pick (Circle of the Land → Land Type,
    # Knowledge Domain → Skill, …).  Auto-saved when the player selects
    # from the variant dropdown so the picker re-hydrates on reload.
    "subclass_choice",
    # Per-class HP gain per level — { class_slug: [int, …] }. Edited via
    # the "HP per Level" table inside the sheet edit panel.
    "hp_rolls",
    # Beast picker favorites — list of Open5e creature slugs starred by
    # the player. Toggled via the ★ button on every picker row.
    "favorite_beasts",
    # Defenses — four string lists. Edited via the chip-toggle UI in
    # the Defenses fieldset; each toggle PATCHes immediately so the
    # state persists without an explicit Save.
    "damage_resistances",
    "damage_immunities",
    "damage_vulnerabilities",
    "condition_immunities",
    # Cached background detail (signature feature etc.) so the sheet's
    # background display block survives a reload without re-fetching.
    "background_data",
    # Feats list — auto-saved on add/remove so the player's selection
    # persists across refreshes without an explicit Save.
    "feats",
}

# Keys that route into a specific entry of ``sheet["classes"]`` when the
# caller passes ``class_slug``.  These are the per-class subclass cache keys.
_CLASS_SCOPED_KEYS = {
    "subclass_features_data",
    "subclass_name",
    "subclass_flavor",
    "subclass_features",
    "subclass_choice",
}


def _apply_sheet_patch(sheet: dict, body: dict) -> dict:
    """Merge whitelisted keys onto a sheet, routing per-class fields into
    the right entry of ``sheet["classes"]`` when ``class_slug`` is supplied."""
    patch = {k: v for k, v in body.items() if k in _SHEET_PATCH_KEYS}
    if not patch:
        return sheet
    cslug = (body.get("class_slug") or "").strip().lower()
    sheet = {**(sheet or {})}
    if cslug:
        # Ensure classes[] exists, then merge per-class keys into the matching entry
        normalize_dnd5e_sheet(sheet)
        classes = list(sheet.get("classes") or [])
        target_idx = next(
            (i for i, c in enumerate(classes)
             if isinstance(c, dict) and _class_slug(c.get("class") or "") == cslug),
            None,
        )
        if target_idx is not None:
            entry = dict(classes[target_idx])
            for k, v in patch.items():
                if k in _CLASS_SCOPED_KEYS:
                    entry[k] = v
            classes[target_idx] = entry
            sheet["classes"] = classes
            # Re-mirror primary onto top-level
            normalize_dnd5e_sheet(sheet)
    # Always merge into top-level too (legacy callers / non-class-scoped keys).
    sheet.update({k: v for k, v in patch.items() if k not in _CLASS_SCOPED_KEYS or not cslug})
    return sheet


@router.patch("/api/campaign/{campaign_id}/character/{char_id}/sheet-fields")
async def patch_sheet_fields(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Merge a small set of pre-approved keys into a character's sheet JSON.

    v2.1.0: when ``hp`` is included in the patch, route through
    ``_apply_hp_change`` so the death save state machine sees the
    transition (e.g. HP dropping to 0 → dying). The optional body field
    ``hp_change_reason`` accepts ``"damage"`` to enable the auto-failure
    tick / massive-damage rule; defaults to a plain set (no damage
    semantics)."""
    body = await request.json()
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Forbidden")

    # Extract HP separately so we can route it through the state machine.
    incoming_hp = body.get("hp") if isinstance(body.get("hp"), dict) else None
    body_for_patch = {k: v for k, v in body.items() if k != "hp"}
    char.sheet = _apply_sheet_patch(char.sheet, body_for_patch)

    hp_result = None
    if incoming_hp is not None and "current" in incoming_hp:
        # Preserve max/temp by writing them first, then routing current
        # through the state machine.
        sheet = dict(char.sheet or {})
        existing_hp = dict(sheet.get("hp") or {})
        if "max" in incoming_hp:
            existing_hp["max"] = int(incoming_hp.get("max") or 0)
        if "temp" in incoming_hp:
            existing_hp["temp"] = max(0, int(incoming_hp.get("temp") or 0))
        sheet["hp"] = existing_hp
        char.sheet = sheet

        reason = str(body.get("hp_change_reason") or "set").lower()
        is_damage = reason == "damage"
        is_crit = bool(body.get("is_crit"))
        damage_amount = int(body.get("damage_amount") or 0)
        hp_result = _apply_hp_change(
            char,
            int(incoming_hp.get("current") or 0),
            is_damage=is_damage,
            is_crit=is_crit,
            damage_amount=damage_amount,
        )

    db.commit()

    if hp_result and hp_result["status_changed"]:
        await hub.broadcast(campaign_id, {
            "type": "character_death_save",
            "data": {
                "character_id": char.id,
                "status": hp_result["death_saves"]["status"],
                "successes": int(hp_result["death_saves"]["successes"]),
                "failures": int(hp_result["death_saves"]["failures"]),
                "hp": hp_result["hp"],
                "source": "sheet_patch",
            },
        })
    return {"ok": True, "hp": hp_result["hp"] if hp_result else None,
            "death_saves": hp_result["death_saves"] if hp_result else None}


# ----------- API: death saving throws (v2.1.0) -----------

@router.post("/api/campaign/{campaign_id}/character/{char_id}/death-save")
async def roll_death_save(
    campaign_id: int,
    char_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Roll a death saving throw for a dying character.

    Per RAW: 10+ = success, <10 = failure, nat 20 wakes the character
    with 1 HP, nat 1 counts as two failures, 3 successes → stable,
    3 failures → dead. The roll lands in the campaign roll log so the
    table sees it.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Forbidden")

    ds = dict((char.sheet or {}).get("death_saves") or {})
    status = ds.get("status") or "alive"
    if status != "dying":
        raise HTTPException(409, f"Character is {status}, not dying — cannot roll a death save")

    successes = int(ds.get("successes") or 0)
    failures = int(ds.get("failures") or 0)

    import random as _random
    raw = _random.randint(1, 20)

    outcome = ""
    regained = False
    if raw == 20:
        outcome = "regain_consciousness"
        regained = True
    elif raw == 1:
        failures += 2
        outcome = "crit_fail"
    elif raw >= 10:
        successes += 1
        outcome = "success"
    else:
        failures += 1
        outcome = "fail"

    if regained:
        # Wake up: HP set to 1, status alive, counters cleared
        hp_result = _apply_hp_change(char, 1)
        new_ds = dict(char.sheet.get("death_saves") or {})
        new_hp = hp_result["hp"]
    else:
        # Threshold checks
        if failures >= 3:
            new_status = "dead"
            successes = 0
            failures = 0
        elif successes >= 3:
            new_status = "stable"
            successes = 0
            failures = 0
        else:
            new_status = "dying"
        _set_death_save_state(char, status=new_status, successes=successes, failures=failures)
        new_ds = dict(char.sheet.get("death_saves") or {})
        new_hp = dict(char.sheet.get("hp") or {})

    # Persist roll record so the campaign log sees it
    note_label = {
        "success": f"💀 Death Save: SUCCESS ({new_ds.get('successes', 0)}/3)",
        "fail": f"💀 Death Save: FAILURE ({new_ds.get('failures', 0)}/3)",
        "crit_fail": "💀 Death Save: CRITICAL FAILURE (2 failures)",
        "regain_consciousness": "💀 Death Save: NATURAL 20 — regain consciousness!",
    }.get(outcome, "💀 Death Save")
    rec = DiceRoll(
        campaign_id=campaign_id,
        user_id=user.id,
        expression="1d20",
        breakdown=f"1d20[{raw}]={raw}  =>  {raw}",
        total=raw,
        visibility=Visibility.PUBLIC,
        note=note_label[:200],
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    # Roller / character info for the broadcast (matches /roll endpoint shape)
    _char_name = char.name
    _portrait_url = char.portrait_url
    _membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id, CampaignMembership.user_id == user.id)
        .first()
    )
    _player_color = (
        _membership.color if _membership and _membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    _user_color = (char.color if char.color else _player_color)

    await hub.broadcast(campaign_id, {
        "type": "roll",
        "data": {
            "id": rec.id,
            "user_id": user.id,
            "user_name": user.display_name,
            "char_name": _char_name,
            "user_color": _user_color,
            "portrait_url": _portrait_url,
            "expression": rec.expression,
            "breakdown": rec.breakdown,
            "total": rec.total,
            "visibility": rec.visibility.value,
            "note": rec.note,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
            "kind": "death_save",
            "death_save_outcome": outcome,
        },
    })
    await hub.broadcast(campaign_id, {
        "type": "character_death_save",
        "data": {
            "character_id": char.id,
            "status": new_ds.get("status"),
            "successes": int(new_ds.get("successes") or 0),
            "failures": int(new_ds.get("failures") or 0),
            "hp": new_hp,
            "source": "roll",
            "outcome": outcome,
            "raw": raw,
        },
    })

    return {
        "ok": True,
        "raw": raw,
        "outcome": outcome,
        "status": new_ds.get("status"),
        "successes": int(new_ds.get("successes") or 0),
        "failures": int(new_ds.get("failures") or 0),
        "hp": new_hp,
    }


@router.post("/api/campaign/{campaign_id}/character/{char_id}/death-save/override")
async def override_death_save(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM-only: manually set a character's death save status and counters.
    Used for narrative beats and misclick recovery. Body: ``{status, successes,
    failures}`` — any field omitted is left alone."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")

    body = await request.json()
    status_in = body.get("status")
    if status_in is not None and status_in not in _DEATH_SAVE_STATUSES:
        raise HTTPException(400, f"status must be one of {_DEATH_SAVE_STATUSES}")

    # If transitioning to "alive" from a 0-HP state, bump HP to 1 so the
    # state is internally consistent (alive at 0 HP would immediately fall
    # back to dying on the next state machine pass).
    if status_in == "alive":
        sheet = dict(char.sheet or {})
        hp = dict(sheet.get("hp") or {})
        if int(hp.get("current") or 0) <= 0:
            hp["current"] = 1
            sheet["hp"] = hp
            char.sheet = sheet

    new_ds = _set_death_save_state(
        char,
        status=status_in,
        successes=body.get("successes"),
        failures=body.get("failures"),
    )
    db.commit()

    await hub.broadcast(campaign_id, {
        "type": "character_death_save",
        "data": {
            "character_id": char.id,
            "status": new_ds.get("status"),
            "successes": int(new_ds.get("successes") or 0),
            "failures": int(new_ds.get("failures") or 0),
            "hp": dict(char.sheet.get("hp") or {}),
            "source": "gm_override",
        },
    })
    return {"ok": True, "death_saves": new_ds, "hp": char.sheet.get("hp")}


@router.post("/api/campaign/{campaign_id}/character/{char_id}/stabilize")
async def stabilize_character(
    campaign_id: int,
    char_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM-only: set a dying character to ``stable``. Equivalent to a
    successful DC 10 Medicine check by an ally (auto-resolution of the
    Medicine roll is deferred to a Phase 3 follow-up)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")

    new_ds = _set_death_save_state(char, status="stable", successes=0, failures=0)
    db.commit()

    await hub.broadcast(campaign_id, {
        "type": "character_death_save",
        "data": {
            "character_id": char.id,
            "status": "stable",
            "successes": 0,
            "failures": 0,
            "hp": dict(char.sheet.get("hp") or {}),
            "source": "stabilize",
        },
    })
    return {"ok": True, "death_saves": new_ds}


# ----------- API: roll-state toggle (v2.2.0) -----------

@router.post("/api/campaign/{campaign_id}/character/{char_id}/roll-state")
async def set_roll_state(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Set or clear a character's roll-state. Body: ``{value: "advantage"
    | "disadvantage" | null}``. While set, single-d20 expressions sent
    through /roll and /attack are auto-upgraded to 2d20kh1 / 2d20kl1
    per the v2.2.0 plan. Manual 2d20kh1 / 2d20kl1 / 1d20a / 1d20d
    submissions remain unchanged and are tagged with "(manual …)" in
    the roll log. Owner or GM only."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Forbidden")

    body = await request.json()
    value = body.get("value")
    if value not in ("advantage", "disadvantage", None):
        raise HTTPException(400, "value must be 'advantage', 'disadvantage', or null")

    sheet = dict(char.sheet or {})
    rs = dict(sheet.get("roll_state") or {})
    rs["value"] = value
    sheet["roll_state"] = rs
    char.sheet = sheet
    db.commit()

    await hub.broadcast(campaign_id, {
        "type": "character_roll_state",
        "data": {
            "character_id": char.id,
            "value": value,
        },
    })
    return {"ok": True, "value": value}


# ----------- WebSocket -----------

@router.websocket("/ws/campaign/{campaign_id}")
async def campaign_ws(websocket: WebSocket, campaign_id: int):
    session = websocket.session  # type: ignore[attr-defined]
    user_id = session.get("user_id") if session else None
    if not user_id:
        await websocket.close(code=4401)
        return
    db = SessionLocal()
    # Audio sync: if a track is currently playing for this campaign, the
    # new client gets the audio_play payload sent privately on connect so
    # they sync to the same seek offset everyone else hears. Built here
    # while the DB session is open; sent below after hub.connect accepts
    # the socket. Targeted send (not broadcast) — broadcasting would
    # restart audio for every other client too.
    initial_audio_payload: dict | None = None
    try:
        user = db.query(User).filter(User.id == user_id).first()
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not user or not campaign or not _user_can_view_campaign(db, user, campaign):
            await websocket.close(code=4403)
            return
        if campaign.now_playing_track_id:
            track = (
                db.query(PlaylistTrack)
                .filter(PlaylistTrack.id == campaign.now_playing_track_id)
                .first()
            )
            if track:
                from .audio_routes import _now_playing_payload
                initial_audio_payload = {
                    "type": "audio_play",
                    "data": _now_playing_payload(campaign, track),
                }
    finally:
        db.close()

    await hub.connect(campaign_id, websocket)

    if initial_audio_payload is not None:
        import json as _json
        try:
            await websocket.send_text(_json.dumps(initial_audio_payload, default=str))
        except Exception as exc:
            log.warning("audio sync send failed for campaign %s: %s", campaign_id, exc)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning("ws error: %s", e)
    finally:
        await hub.disconnect(campaign_id, websocket)


# ----------- Player character roster + standalone sheet -----------

@router.get("/campaign/{campaign_id}/characters", response_class=HTMLResponse)
def player_characters(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Character roster — accessible without an active session."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    is_gm = _user_is_gm(user, campaign, db)
    if is_gm:
        characters = (
            db.query(Character)
            .filter(Character.campaign_id == campaign_id)
            .order_by(Character.name)
            .all()
        )
    else:
        characters = (
            db.query(Character)
            .filter(
                Character.campaign_id == campaign_id,
                Character.owner_user_id == user.id,
            )
            .order_by(Character.name)
            .all()
        )
    # Build owner name map for GM view
    owner_names: dict[int, str] = {}
    if is_gm:
        owner_ids = {c.owner_user_id for c in characters if c.owner_user_id}
        if owner_ids:
            for u in db.query(User).filter(User.id.in_(owner_ids)).all():
                owner_names[u.id] = u.display_name
    return templates.TemplateResponse(
        "my_characters.html",
        {
            "request": request,
            "user": user,
            "campaign": campaign,
            "characters": characters,
            "is_gm": is_gm,
            "owner_names": owner_names,
            "system": get_system(campaign.game_system),
        },
    )


@router.get("/campaign/{campaign_id}/character/{char_id}/sheet", response_class=HTMLResponse)
def character_sheet_page(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Standalone full-page character sheet — no active session required."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    is_gm = _user_is_gm(user, campaign, db)
    can_edit = is_gm or char.owner_user_id == user.id
    sheet_template = "sheet_dnd5e.html" if char.template == "dnd5e" else "sheet_generic.html"
    page_sheet = char.sheet or get_template(char.template)
    if char.template == "dnd5e":
        normalize_dnd5e_sheet(page_sheet)
    return templates.TemplateResponse(
        "character_page.html",
        {
            "request": request,
            "user": user,
            "campaign": campaign,
            "char": char,
            "sheet": page_sheet,
            "can_edit": can_edit,
            "is_gm": is_gm,
            "sheet_template": sheet_template,
            "system": get_system(campaign.game_system),
            "class_roster": class_levels_summary(page_sheet) if char.template == "dnd5e" else [],
            "animate_gifs": user.animate_gifs,
        },
    )


# ----------- Monster sheet (v2.3.10) -----------
# Reuse sheet_dnd5e.html for monsters by projecting a TokenTemplate (stat
# block + structured actions) into the same context shape the character
# sheet expects. Gives GMs PC-parity click-to-roll for ability checks,
# saves, skills, and structured attacks without rebuilding a parallel UI.
# See docs in monster_page.html + the adapter below.


class _SyntheticMonsterChar:
    """Stand-in for a ``Character`` ORM object so ``sheet_dnd5e.html`` (and
    its wrapper ``monster_page.html``) can render a monster's stat block
    without needing a DB-backed Character row. Only the attributes the
    template actually reads need to exist — see the template scan in
    docs/plans/monster-sheet.md (when written) or grep ``char\\.`` in
    ``app/templates/sheet_dnd5e.html`` to confirm the surface.

    Intentionally NOT a SQLAlchemy model: the monster lives in
    ``TokenTemplate`` (and optionally a homebrew JSON file), not in
    ``characters``. Saving to the character API would 404, so the
    monster sheet renders with ``can_edit=False`` and the form's
    data-readonly flag suppresses save buttons.
    """

    __slots__ = (
        "id", "name", "sheet", "template", "owner_user_id", "campaign_id",
        "color", "portrait_url", "ring_style", "template_id",
    )

    def __init__(
        self,
        *,
        id,
        name: str,
        sheet: dict,
        template: str = "dnd5e",
        owner_user_id: int = 0,
        campaign_id: int = 0,
        color: Optional[str] = None,
        portrait_url: Optional[str] = None,
        ring_style: Optional[str] = None,
        template_id: Optional[int] = None,
    ) -> None:
        # ``id`` may be a numeric TokenTemplate primary key (used by the
        # 2.3.10 standalone monster sheet route) or a string like
        # ``"monster-22"`` (used by the 2.3.17 mini-sheet pool, where DOM
        # ids need to NOT collide with real Character primary keys). The
        # partial stamps it into ``id=`` / ``data-char-id=`` attributes
        # directly; downstream JS parses or branches as needed.
        self.id = id
        self.name = name
        self.sheet = sheet
        self.template = template
        self.owner_user_id = owner_user_id
        self.campaign_id = campaign_id
        self.color = color or "#888"
        self.portrait_url = portrait_url
        self.ring_style = ring_style or "solid"
        # ``template_id``: the underlying TokenTemplate primary key as an
        # int, even when ``id`` is the string form. The mini-sheet partial
        # uses this to build the ``/monster-template/{tid}/sheet`` URL
        # for the "Open full sheet" link without needing to parse the
        # ``"monster-N"`` prefix off ``id``.
        self.template_id = template_id


def _monster_dict_to_sheet(m: dict, *, base: Optional[dict] = None) -> dict:
    """Project a Monster Pydantic dict (loaded by ``local_content.resolve``
    from ``app/data/local/dnd5e/monsters/*.json`` or a homebrew JSON file)
    into the sheet dict shape ``sheet_dnd5e.html`` consumes.

    ``base`` is the TokenTemplate's existing sheet — any keys it carries
    that we don't compute here (notes, custom overrides, etc.) pass
    through unchanged. Anything we compute (HP, AC, abilities, speed,
    race header, damage lists, actions) overrides the base.
    """
    import re as _re
    out = dict(base or {})
    hp = int(m.get("hit_points") or 10)
    out["hp"] = {"current": hp, "max": hp, "temp": 0}
    out["ac"] = int(m.get("armor_class") or 10)
    speed_raw = m.get("speed") or {}
    if isinstance(speed_raw, dict):
        walk = speed_raw.get("walk") or 30
        out["speed"] = int(walk) if str(walk).isdigit() else 30
    else:
        digits = _re.search(r"\d+", str(speed_raw))
        out["speed"] = int(digits.group()) if digits else 30
    out["abilities"] = {
        "STR": int(m.get("strength") or 10),
        "DEX": int(m.get("dexterity") or 10),
        "CON": int(m.get("constitution") or 10),
        "INT": int(m.get("intelligence") or 10),
        "WIS": int(m.get("wisdom") or 10),
        "CHA": int(m.get("charisma") or 10),
    }
    size = (m.get("size") or "").strip()
    type_ = (m.get("type") or "").strip()
    header_bits = " ".join(b for b in (size, type_) if b)
    if header_bits:
        out["race"] = header_bits
    if m.get("alignment"):
        out["background"] = m.get("alignment")
    for key in ("damage_resistances", "damage_immunities",
                "damage_vulnerabilities", "condition_immunities"):
        raw = m.get(key)
        if isinstance(raw, str) and raw.strip():
            out[key] = [p.strip() for p in _re.split(r"[,;]", raw) if p.strip()]
        elif isinstance(raw, list):
            out[key] = [str(p) for p in raw]
    # Pass the structured actions through so the caller's fold step picks
    # them up. Caller handles attack-button projection.
    if m.get("actions"):
        out["actions"] = m.get("actions")
    return out


def _monster_template_to_sheet(tmpl: TokenTemplate, campaign_id: int) -> dict:
    """Project a monster TokenTemplate's stat block + structured actions
    into the dict shape that ``sheet_dnd5e.html`` consumes.

    Source resolution order:

    1. ``tmpl.sheet["monster_slug"]`` — if the template is a pointer to a
       shipped or homebrew monster (the minimal demo NPC seed shape — see
       ``app/demo_seed.py _npc_sheet``), resolve via ``local_content`` and
       overlay the full stat block. The pointer pattern keeps the
       TokenTemplate rows tiny and the stat-block authoring in one place.

    2. ``tmpl.sheet["actions"]`` (homebrew structured Action shape from the
       v2.3.8 editor) and/or ``tmpl.sheet["attacks"]`` (legacy regex-
       derived character schema from SRD imports via
       ``_open5e_to_dnd5e_sheet``). The former gets folded into the latter
       so the character template, which reads ``sheet.attacks``, sees a
       unified list. De-duped by name so a homebrew override shadows an
       SRD-imported same-name attack.

    For SRD monsters where the Action's ``attack_bonus`` is null (shipped
    files describe the to-hit only in the desc text), the projection regex-
    extracts ``+N to hit`` from the desc so the attack button rolls
    ``1d20+N`` instead of a raw 1d20.
    """
    import re as _re

    sheet = dict(tmpl.sheet or {})
    monster_slug = sheet.get("monster_slug")
    if monster_slug:
        resolved = local_content.resolve(
            str(monster_slug), type="monsters", campaign_id=campaign_id,
        )
        if resolved is not None:
            monster_dict, _src = resolved
            sheet = _monster_dict_to_sheet(monster_dict, base=sheet)

    actions = sheet.get("actions") or []
    if not actions:
        return sheet

    existing_attacks = list(sheet.get("attacks") or [])
    by_name = {
        (a.get("name") or "").strip().lower(): i
        for i, a in enumerate(existing_attacks)
        if isinstance(a, dict)
    }

    for a in actions:
        if not isinstance(a, dict):
            continue
        if not (a.get("attack_roll") or a.get("damage") or a.get("save_ability")):
            continue
        name = (a.get("name") or "Action").strip()
        save_ability_raw = (a.get("save_ability") or "").strip().upper()
        atk_bonus = a.get("attack_bonus") or ""
        # SRD fallback: shipped monsters set attack_roll=true but leave
        # attack_bonus null — the to-hit lives in the desc text. Regex it
        # out so the attack button does ``1d20+N`` instead of raw 1d20.
        if a.get("attack_roll") and not atk_bonus:
            bonus_m = _re.search(r"([+-]\d+)\s*to hit", a.get("desc") or "")
            if bonus_m:
                atk_bonus = bonus_m.group(1)
        atk_entry = {
            # v2.3.40: pass through the structured Action's ``id`` so the
            # client can key per-combatant charge state (combatant.
            # action_charges[action_id]) and ``charges_max`` so the init-
            # tracker view can render the N/M counter + disable buttons
            # when the action is spent.
            "id": a.get("id") or name.lower().replace(" ", "-"),
            "name": name,
            "atk_bonus": atk_bonus,
            "damage": a.get("damage") or "",
            "damage_type": a.get("damage_type") or "",
            "save_dc": (a.get("save_dc") or None) if a.get("save_dc") else None,
            "save_ability": save_ability_raw or None,
            "charges_max": int(a.get("charges_max") or 0),
            "description": a.get("desc") or "",
        }
        key = name.lower()
        if key in by_name:
            existing_attacks[by_name[key]] = atk_entry
        else:
            existing_attacks.append(atk_entry)
            by_name[key] = len(existing_attacks) - 1

    sheet["attacks"] = existing_attacks
    return sheet


@router.get(
    "/campaign/{campaign_id}/monster-template/{template_id}/sheet",
    response_class=HTMLResponse,
)
def monster_template_sheet_page(
    campaign_id: int,
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.3.10: full sheet view for a monster ``TokenTemplate``, reusing
    ``sheet_dnd5e.html`` so the GM gets PC-parity click-to-roll for
    ability checks, saves, skills, and structured attacks.

    GM-only because monsters are GM-visibility data in this codebase.
    Read-only — ``can_edit=False`` makes the sheet's form render with
    ``data-readonly="1"``, which the sheet JS uses to suppress save
    buttons. The form fields stay populated though, because
    ``wireDnd5eRollButtons`` reads ability/skill/save state via
    ``form.querySelector('[name="..."]').value``.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    tmpl = (
        db.query(TokenTemplate)
        .filter(TokenTemplate.id == template_id,
                TokenTemplate.campaign_id == campaign_id)
        .first()
    )
    if not tmpl:
        raise HTTPException(404, "Monster template not found")

    sheet = _monster_template_to_sheet(tmpl, campaign_id)
    if (tmpl.template or "dnd5e") == "dnd5e":
        normalize_dnd5e_sheet(sheet)
    sheet_template = (
        "sheet_dnd5e.html"
        if (tmpl.template or "dnd5e") == "dnd5e"
        else "sheet_generic.html"
    )
    # v2.3.42: surface the homebrew slug to the template so it can render
    # an "✏️ Edit" link in the breadcrumb that bounces the GM to the
    # campaign-settings homebrew editor (anchored to the right entry).
    # Only set when (a) the TokenTemplate points to a slug via
    # ``sheet.monster_slug`` AND (b) the resolver tags the source as
    # ``local-homebrew`` (not shipped SRD, not Open5e cache) — editing
    # SRD content through the homebrew editor would silently fork it,
    # which is what the existing "📋 Clone" button already does
    # explicitly. ``raw_sheet`` reads the original sheet because
    # ``_monster_template_to_sheet`` overlays the resolved monster onto
    # ``sheet`` and the slug pointer survives the overlay too, but
    # reading from the original keeps the intent obvious.
    edit_homebrew_slug: Optional[str] = None
    raw_sheet = tmpl.sheet or {}
    raw_slug = raw_sheet.get("monster_slug")
    if raw_slug:
        resolved = local_content.resolve(
            str(raw_slug), type="monsters", campaign_id=campaign_id,
        )
        if resolved is not None and resolved[1] == "local-homebrew":
            edit_homebrew_slug = str(raw_slug)
    synthetic = _SyntheticMonsterChar(
        id=template_id,
        name=tmpl.name or "Monster",
        sheet=sheet,
        template=tmpl.template or "dnd5e",
        owner_user_id=0,
        campaign_id=campaign_id,
        portrait_url=tmpl.image_url,
    )
    return templates.TemplateResponse(
        "monster_page.html",
        {
            "request": request,
            "user": user,
            "campaign": campaign,
            "char": synthetic,
            "sheet": sheet,
            "can_edit": False,
            "is_gm": True,
            "sheet_template": sheet_template,
            "system": get_system(campaign.game_system),
            "class_roster": [],
            "animate_gifs": user.animate_gifs,
            # v2.3.13: lets sheet_dnd5e.html hide PC-only sections
            # (spells, inventory, class/subclass/race features, class
            # resources, notes) that have no meaning for a monster.
            "is_monster_sheet": True,
            # v2.3.42: homebrew slug for the "✏️ Edit" breadcrumb link;
            # None for SRD / Open5e monsters or templates without a
            # monster_slug pointer (those use Clone-then-edit flow).
            "edit_homebrew_slug": edit_homebrew_slug,
        },
    )


# ----------- Settings: characters (GM) -----------

_SETTINGS_UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "static" / "uploads"
_MAP_DIR = _SETTINGS_UPLOAD_ROOT / "maps"
_ALLOWED_IMG = {"image/png", "image/jpeg", "image/webp", "image/gif", "video/webm", "video/mp4"}


def _make_map_thumbnail(data: bytes, content_type: str, map_dir: Path, stem: str) -> Optional[str]:
    """Return a static JPEG thumbnail URL for GIFs (frame 0) and videos (ffmpeg).
    Returns None for static images — callers fall back to image_url."""
    if content_type == "image/gif":
        try:
            import io as _io
            from PIL import Image as _PIL
            with _PIL.open(_io.BytesIO(data)) as im:
                im.seek(0)
                frame = im.convert("RGB")
                thumb_name = stem + "_thumb.jpg"
                frame.save(str(map_dir / thumb_name), "JPEG", quality=80)
                return f"/static/uploads/maps/{thumb_name}"
        except Exception:
            return None
    if content_type in ("video/mp4", "video/webm"):
        try:
            import subprocess, tempfile, os as _os
            thumb_name = stem + "_thumb.jpg"
            thumb_path = map_dir / thumb_name
            with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as tf:
                tf.write(data)
                tf_path = tf.name
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-ss", "0.5", "-i", tf_path,
                     "-vframes", "1", "-q:v", "3", str(thumb_path)],
                    capture_output=True, timeout=30, check=True,
                )
                return f"/static/uploads/maps/{thumb_name}"
            finally:
                try:
                    _os.unlink(tf_path)
                except Exception:
                    pass
        except Exception:
            return None
    return None


@router.post("/campaign/{campaign_id}/settings/characters")
def settings_create_character(
    campaign_id: int,
    name: str = Form(...),
    owner_user_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    sys = get_system(campaign.game_system)
    char = Character(
        campaign_id=campaign_id,
        name=name.strip()[:120] or "New character",
        template=sys.sheet_template,
        sheet=get_template(sys.sheet_template),
        owner_user_id=owner_user_id or None,
    )
    db.add(char)
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#characters", status_code=303)


@router.post("/campaign/{campaign_id}/settings/characters/{char_id}/assign")
def settings_assign_character(
    campaign_id: int,
    char_id: int,
    owner_user_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    char = db.query(Character).filter(Character.id == char_id, Character.campaign_id == campaign_id).first()
    if not char:
        raise HTTPException(404)
    char.owner_user_id = owner_user_id or None
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#characters", status_code=303)


@router.post("/campaign/{campaign_id}/settings/characters/{char_id}/delete")
def settings_delete_character(
    campaign_id: int,
    char_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    char = db.query(Character).filter(Character.id == char_id, Character.campaign_id == campaign_id).first()
    if not char:
        raise HTTPException(404)
    char.campaign_id = None
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#characters", status_code=303)


@router.post("/campaign/{campaign_id}/settings/characters/import")
def settings_import_character(
    campaign_id: int,
    source_char_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM imports (copies) a player's character from another campaign into this one."""
    import copy as _copy
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    source = db.query(Character).filter(Character.id == source_char_id).first()
    if not source:
        raise HTTPException(404, "Character not found")
    new_char = Character(
        campaign_id=campaign_id,
        name=source.name,
        template=source.template,
        sheet=_copy.deepcopy(source.sheet or {}),
        portrait_url=source.portrait_url,
        owner_user_id=source.owner_user_id,
    )
    db.add(new_char)
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#characters", status_code=303)


# ----------- Settings: maps (GM) -----------

@router.post("/campaign/{campaign_id}/settings/maps")
async def settings_upload_map(
    campaign_id: int,
    name: str = Form(...),
    grid_type: str = Form("square"),
    grid_size_px: int = Form(70),
    width_px: int = Form(2000),
    height_px: int = Form(1500),
    tags: str = Form(""),
    folder: str = Form(""),
    # v2.4.0: per-map "show grid overlay" toggle. HTML-checkbox idiom —
    # unchecked boxes don't submit the field at all, so ``Form(False)``
    # captures "off" while the template ships the box ``checked`` by
    # default. New uploads default to overlay-on, matching legacy maps
    # whose v53 migration backfills ``show_grid = TRUE``.
    show_grid: bool = Form(False),
    image: UploadFile = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    if image and image.filename:
        if image.content_type not in _ALLOWED_IMG:
            raise HTTPException(400, "Unsupported image type")
        data = await image.read()
        if len(data) > 80 * 1024 * 1024:
            raise HTTPException(400, "Map image too large (>80 MB)")
        _MAP_DIR.mkdir(parents=True, exist_ok=True)
        ext = Path(image.filename).suffix.lower() or ".png"
        stem = uuid.uuid4().hex
        fname = f"{stem}{ext}"
        (_MAP_DIR / fname).write_bytes(data)
        image_url = f"/static/uploads/maps/{fname}"
        if image.content_type and image.content_type.startswith("image/"):
            try:
                import io as _io
                from PIL import Image as _PILImage
                with _PILImage.open(_io.BytesIO(data)) as _img:
                    width_px, height_px = _img.size
            except Exception:
                pass
        thumbnail_url = _make_map_thumbnail(data, image.content_type or "", _MAP_DIR, stem)
    try:
        gt = GridType(grid_type)
    except ValueError:
        gt = GridType.SQUARE
    m = Map(
        campaign_id=campaign_id,
        name=name.strip()[:120] or "Map",
        image_url=image_url,
        thumbnail_url=thumbnail_url,
        grid_type=gt,
        grid_size_px=max(20, min(grid_size_px, 300)),
        width_px=max(200, min(width_px, 8000)),
        height_px=max(200, min(height_px, 8000)),
        tags=_parse_tags(tags),
        folder=folder.strip()[:120],
        show_grid=show_grid,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    if not campaign.active_map_id:
        campaign.active_map_id = m.id
        db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#maps", status_code=303)


@router.post("/campaign/{campaign_id}/settings/maps/{map_id}/rename")
async def settings_rename_map(
    campaign_id: int,
    map_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Rename a map in place. GM-only. Body: ``{name: str}``. Empty /
    whitespace-only names are rejected so the table row doesn't render
    as a blank line."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    m = db.query(Map).filter(Map.id == map_id, Map.campaign_id == campaign_id).first()
    if not m:
        raise HTTPException(404)
    body = await request.json()
    new_name = str(body.get("name") or "").strip()[:120]
    if not new_name:
        raise HTTPException(400, "Map name cannot be empty")
    m.name = new_name
    db.commit()
    return {"ok": True, "name": m.name}


@router.post("/campaign/{campaign_id}/settings/maps/{map_id}/grid_size")
async def settings_map_grid_size(
    campaign_id: int,
    map_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    m = db.query(Map).filter(Map.id == map_id, Map.campaign_id == campaign_id).first()
    if not m:
        raise HTTPException(404)
    body = await request.json()
    val = max(20, min(300, int(body.get("grid_size_px", 70))))
    m.grid_size_px = val
    db.commit()
    return {"ok": True, "grid_size_px": m.grid_size_px}


@router.post("/campaign/{campaign_id}/settings/maps/{map_id}/show_grid")
async def settings_map_show_grid(
    campaign_id: int,
    map_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.4.0: toggle the per-map grid-overlay flag. GM-only. Body:
    ``{show_grid: bool}``. Token snapping continues to follow
    ``grid_type`` (square / hex / none) regardless of this flag — the
    overlay is purely a visual layer for maps whose background image
    doesn't already include a grid."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    m = db.query(Map).filter(Map.id == map_id, Map.campaign_id == campaign_id).first()
    if not m:
        raise HTTPException(404)
    body = await request.json()
    m.show_grid = bool(body.get("show_grid", True))
    db.commit()
    return {"ok": True, "show_grid": m.show_grid}


@router.post("/campaign/{campaign_id}/settings/maps/{map_id}/tags")
async def settings_set_map_tags(
    campaign_id: int,
    map_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Replace the map's tag list. GM-only. Body accepts either a JSON
    array or a comma-separated string; same normalisation as encounter
    and playlist tags (trim, dedupe case-insensitive, 40-char cap each,
    ≤20 entries)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    m = db.query(Map).filter(Map.id == map_id, Map.campaign_id == campaign_id).first()
    if not m:
        raise HTTPException(404)
    body = await request.json()
    m.tags = _parse_tags(body.get("tags"))
    db.commit()
    return {"ok": True, "tags": m.tags}


@router.post("/campaign/{campaign_id}/settings/maps/{map_id}/folder")
async def settings_set_map_folder(
    campaign_id: int,
    map_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Set the map's folder. GM-only. Body: ``{folder: str}``."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    m = db.query(Map).filter(Map.id == map_id, Map.campaign_id == campaign_id).first()
    if not m:
        raise HTTPException(404)
    body = await request.json()
    m.folder = (body.get("folder") or "").strip()[:120]
    db.commit()
    return {"ok": True, "folder": m.folder}


@router.post("/campaign/{campaign_id}/settings/maps/{map_id}/activate")
def settings_activate_map(
    campaign_id: int,
    map_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    m = db.query(Map).filter(Map.id == map_id, Map.campaign_id == campaign_id).first()
    if not m:
        raise HTTPException(404)
    campaign.active_map_id = m.id
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#maps", status_code=303)


@router.post("/campaign/{campaign_id}/settings/maps/{map_id}/delete")
def settings_delete_map(
    campaign_id: int,
    map_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    m = db.query(Map).filter(Map.id == map_id, Map.campaign_id == campaign_id).first()
    if not m:
        raise HTTPException(404)
    if campaign.active_map_id == m.id:
        campaign.active_map_id = None
    db.delete(m)
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#maps", status_code=303)


# ----------- Settings: members + danger zone (admin) -----------

@router.post("/campaign/{campaign_id}/settings/members/add")
def settings_add_member(
    campaign_id: int,
    user_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404)
    existing = db.query(CampaignMembership).filter(
        CampaignMembership.campaign_id == campaign_id,
        CampaignMembership.user_id == user_id,
    ).first()
    if not existing:
        db.add(CampaignMembership(campaign_id=campaign_id, user_id=user_id))
        db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#members", status_code=303)


@router.post("/campaign/{campaign_id}/settings/members/{membership_id}/remove")
def settings_remove_member(
    campaign_id: int,
    membership_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    db.query(CampaignMembership).filter(
        CampaignMembership.id == membership_id,
        CampaignMembership.campaign_id == campaign_id,
    ).delete()
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#members", status_code=303)


@router.post("/campaign/{campaign_id}/settings/delete")
def settings_delete_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404)
    c.active_map_id = None
    db.commit()
    db.delete(c)
    db.commit()
    return RedirectResponse("/", status_code=303)
