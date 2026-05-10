"""Tabletop pages + REST/WebSocket APIs.

REST is used for state-changing actions (move token, roll dice, edit sheet).
The WebSocket pushes those changes to other connected clients.
"""
from __future__ import annotations

import logging
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
    Campaign,
    CampaignMembership,
    Character,
    ConcentrationEffect,
    DiceRoll,
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
from ..sheet_templates import get_template
from ..templates import templates


router = APIRouter()
log = logging.getLogger(__name__)

# In-memory heal-claim store (cast_id → claim dict). Entries expire after 8 h.
_heal_claims: dict[str, dict] = {}

def _purge_heal_claims() -> None:
    now = _time.time()
    for k in [k for k, v in _heal_claims.items() if v["expires"] < now]:
        del _heal_claims[k]


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
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member of this campaign")
    is_gm = _user_is_gm(user, campaign, db)
    # Session gate: players (non-GM members) only see the tabletop while the
    # GM has the session active. They get a "waiting" page that auto-redirects
    # via WebSocket the moment the GM hits Start.
    if not is_gm and not campaign.session_active:
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
    rolls = (
        db.query(DiceRoll)
        .filter(DiceRoll.campaign_id == campaign.id)
        .order_by(DiceRoll.created_at.desc())
        .limit(100)
        .all()
    )
    visible_rolls = [r for r in rolls if _filter_roll_for_user(r, user, campaign, db)]
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
    tmpl_objs = db.query(TokenTemplate).filter(TokenTemplate.campaign_id == campaign.id).order_by(TokenTemplate.name).all()
    char_data = [{"id": c.id, "name": c.name, "owner_user_id": c.owner_user_id, "template": c.template, "sheet": c.sheet or {}} for c in characters]
    token_data = [_token_dict(t) for t in tokens]
    tmpl_data = [{"id": t.id, "name": t.name, "image_url": t.image_url, "tags": t.tags or [], "template": t.template, "sheet": t.sheet or {}} for t in tmpl_objs]
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
            "char_data": char_data,
            "token_data": token_data,
            "tmpl_data": tmpl_data,
            "user_color_map": user_color_map,
            "user_portrait_map": user_portrait_map,
            "user_char_name_map": user_char_name_map,
            "conc_by_char": conc_by_char,
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
        },
    )


_VALID_CAMPAIGN_FONTS = {"", "lora", "cormorant", "im-fell"}


@router.post("/campaign/{campaign_id}/settings")
async def campaign_settings_save(
    campaign_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    game_system: str = Form("generic"),
    gm_tab_color: str = Form(""),
    font_override: str = Form(""),
    thumbnail: UploadFile = File(None),
    clear_thumbnail: bool = Form(False),
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
    if clear_thumbnail:
        campaign.thumbnail_url = None
    if thumbnail and thumbnail.filename:
        from ..routes.admin_routes import _save_thumbnail
        campaign.thumbnail_url = await _save_thumbnail(thumbnail)
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings", status_code=303)


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
    an already-active session is a no-op except it refreshes started_at."""
    from datetime import datetime as _dt
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    campaign.session_active = True
    campaign.session_started_at = _dt.utcnow()
    db.commit()
    await hub.broadcast(campaign_id, {"type": "session_started", "data": {}})
    return RedirectResponse(f"/campaign/{campaign_id}", status_code=303)


@router.post("/campaign/{campaign_id}/session/end")
async def end_session(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM (or admin) closes the tabletop. Players in the tabletop will be
    bounced back to the lobby; new players hitting the URL get the
    waiting page until the GM Starts again."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    campaign.session_active = False
    db.commit()
    await hub.broadcast(campaign_id, {"type": "session_ended", "data": {}})
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
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Place a character's token on the active map (character owner or GM).
    If the character already has a token on this map it is replaced.
    Token image is pre-filled from the character's portrait if one is set."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    if not campaign.active_map_id:
        raise HTTPException(400, "No active map")
    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not _user_is_gm(user, campaign, db) and char.owner_user_id != user.id:
        raise HTTPException(403, "Cannot place this character's token")

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
    cx = round((active_map.width_px / 2) / gsize) * gsize if active_map else 0
    cy = round((active_map.height_px / 2) / gsize) * gsize if active_map else 0

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
    """Remove a character's token from the active map (character owner or GM)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not _user_is_gm(user, campaign, db) and char.owner_user_id != user.id:
        raise HTTPException(403, "Cannot remove this character's token")
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
    try:
        visibility = Visibility(visibility_str)
    except ValueError:
        raise HTTPException(400, "Invalid visibility")
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
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
    # Look up roller's character, then resolve color (char > player > gm) and portrait
    _char = (
        db.query(Character)
        .filter(Character.campaign_id == campaign_id, Character.owner_user_id == user.id)
        .first()
    )
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
            },
        },
    )
    return {"ok": True, "total": rec.total, "breakdown": rec.breakdown}


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

    # Decrement slot when this is a leveled spell (cantrips are free)
    updated_slot = None
    if spell_level >= 1:
        slots = dict(sheet.get("spell_slots") or {})
        slot_key = str(slot_level)
        slot = dict(slots.get(slot_key) or {"total": 0, "used": 0})
        total = int(slot.get("total") or 0)
        used = int(slot.get("used") or 0)
        if total <= 0 or used >= total:
            return JSONResponse(
                status_code=409,
                content={"error": "no_slot", "level": slot_level, "spell_name": spell.get("name", "")},
            )
        slot["used"] = used + 1
        slots[slot_key] = slot
        sheet["spell_slots"] = slots
        char.sheet = sheet
        db.commit()
        updated_slot = {"level": slot_level, "total": total, "used": slot["used"]}

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
        "spell_desc": spell.get("desc", "") or spell.get("description", ""),
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
                "level": updated_slot["level"],
                "total": updated_slot["total"],
                "used": updated_slot["used"],
            },
        })
    return {"ok": True, "id": cast_id, "slot": updated_slot}


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

    # Apply HP (capped at max)
    sheet = dict(char.sheet or {})
    hp = dict(sheet.get("hp") or {})
    hp_cur = int(hp.get("current") or 0)
    hp_max = int(hp.get("max") or 0)
    new_cur = min(hp_max, hp_cur + rolled) if hp_max > 0 else (hp_cur + rolled)
    hp["current"] = new_cur
    sheet["hp"] = hp
    char.sheet = sheet
    db.commit()

    # Track claim
    claimed.add(user.id)
    claimed_count = len(claimed)

    new_hp = {"current": new_cur, "max": hp_max, "temp": int(hp.get("temp") or 0)}
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
    hp = dict(sheet.get("hp") or {})
    hp_max = int(hp.get("max") or 0)
    hp_cur = int(hp.get("current") or 0)
    hd = dict(sheet.get("hit_dice") or {})
    hd_max = int(hd.get("max") if hd.get("max") is not None else (sheet.get("level") or 1))
    hd_cur = int(hd.get("current") if hd.get("current") is not None else hd_max)

    if rest_type == "long":
        hp["current"] = hp_max if hp_max > 0 else hp_cur
        hp["temp"] = 0
        hd["max"] = hd_max
        hd["current"] = min(hd_max, hd_cur + max(1, hd_max // 2)) if hd_max > 0 else hd_cur
        slots = dict(sheet.get("spell_slots") or {})
        new_slots = {}
        for k, v in slots.items():
            if isinstance(v, dict):
                new_slots[k] = {**v, "used": 0}
            else:
                new_slots[k] = v
        sheet["spell_slots"] = new_slots
        sheet["hp"] = hp
        sheet["hit_dice"] = hd
        char.sheet = sheet
        db.commit()

        # Broadcast slot-pip updates so any open sheet / mini-sheet re-renders
        for k, v in new_slots.items():
            if isinstance(v, dict) and int(v.get("total") or 0) > 0:
                try:
                    await hub.broadcast(campaign_id, {
                        "type": "spell_slot_update",
                        "data": {
                            "character_id": char.id,
                            "level": int(k),
                            "total": int(v.get("total") or 0),
                            "used": 0,
                        },
                    })
                except Exception:
                    pass

        return {"ok": True, "type": "long", "hp": hp, "hit_dice": hd}

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
    hp["current"] = new_hp
    hd["current"] = hd_cur - 1
    hd["max"] = hd_max
    sheet["hp"] = hp
    sheet["hit_dice"] = hd
    char.sheet = sheet
    db.commit()

    return {
        "ok": True,
        "type": "short",
        "hp": hp,
        "hit_dice": hd,
        "expression": expr,
        "recovered": recovered,
        "breakdown": breakdown,
    }


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
    if not is_save and attack_bonus_raw:
        bonus_expr = attack_bonus_raw if attack_bonus_raw.startswith(("+", "-"))\
            or any(c.isalpha() for c in attack_bonus_raw)\
            else "+" + attack_bonus_raw
        atk_expr = "1d20" + (bonus_expr if bonus_expr.startswith(("+", "-")) else "+" + bonus_expr)
        try:
            r = dice_mod.roll(atk_expr)
            attack_total = r.total
            attack_breakdown = r.breakdown
        except dice_mod.DiceParseError:
            attack_total = None
            attack_breakdown = ""
    elif not is_save:
        # No bonus given — flat d20
        try:
            r = dice_mod.roll("1d20")
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
    }
    await hub.broadcast(campaign_id, {"type": "weapon_attack", "data": payload})
    return {"ok": True, "id": attack_id}


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
            f"https://api.open5e.com/v2/creatures/{slug}/",
            headers={"User-Agent": "SimpleVTT/1.0"},
        )
        with _urlreq.urlopen(req, timeout=10) as r:
            monster = _json.loads(r.read())
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    sheet = _open5e_to_dnd5e_sheet(monster)
    tags = [t for t in [monster.get("type", ""), monster.get("size", ""), f"CR {monster.get('challenge_rating', '0')}"] if t]
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


@router.get("/api/open5e/monsters")
def open5e_monsters_proxy(search: str = "", limit: int = 20):
    import json as _json
    import urllib.parse as _urlparse
    import urllib.request as _urlreq
    qs = _urlparse.urlencode({"search": search, "limit": min(abs(limit), 50)})
    url = f"https://api.open5e.com/v2/creatures/?{qs}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    results = []
    for m in data.get("results", []):
        ac = m.get("armor_class", 10)
        if isinstance(ac, list) and ac:
            ac = ac[0].get("value", 10) if isinstance(ac[0], dict) else ac[0]
        results.append({
            "slug": m.get("key", m.get("slug", "")),
            "name": m.get("name", ""),
            "cr": str(m.get("challenge_rating", "0")),
            "type": m.get("type", ""),
            "size": m.get("size", ""),
            "hp": m.get("hit_points", 0),
            "ac": ac,
            "source": m.get("document__title", m.get("document", {}).get("title", "") if isinstance(m.get("document"), dict) else ""),
        })
    return {"count": data.get("count", 0), "results": results}


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
def open5e_class_detail(slug: str = ""):
    from ..open5e_local import is_ready, get_class
    if not slug:
        raise HTTPException(400, "slug required")
    if is_ready():
        c = get_class(slug)
        if c:
            return _class_detail_response(c)
    import json as _json, urllib.request as _urlreq
    try:
        req = _urlreq.Request(f"https://api.open5e.com/v1/classes/{slug}/",
                              headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            c = _json.loads(r.read())
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    return _class_detail_response(c)


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
def open5e_subclass_detail(slug: str = "", class_slug: str = ""):
    from ..open5e_local import is_ready, get_subclass
    if not slug:
        raise HTTPException(400, "slug required")
    if is_ready():
        s = get_subclass(slug)
        if s:
            return _subclass_response(s)
    import json as _json, urllib.request as _urlreq

    def _req(url: str) -> dict:
        r = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(r, timeout=8) as resp:
            return _json.loads(resp.read())

    # Primary: v1/subclasses/{slug}/
    try:
        s = _req(f"https://api.open5e.com/v1/subclasses/{slug}/")
        return _subclass_response(s)
    except Exception:
        pass

    # Fallback: find the archetype inside the parent class detail
    if class_slug:
        try:
            data = _req(f"https://api.open5e.com/v1/classes/{class_slug}/")
            archetypes = data.get("archetypes") or data.get("subclasses") or []
            for a in archetypes:
                if a.get("slug") == slug or a.get("name", "").lower() == slug.replace("-", " "):
                    return _subclass_response(a)
        except Exception:
            pass

    return {"text": "", "name": "", "flavor": "", "features": []}


@router.get("/api/open5e/race-detail")
def open5e_race_detail(slug: str = ""):
    from ..open5e_local import is_ready, get_race, format_race_text, parse_race_traits
    if not slug:
        raise HTTPException(400, "slug required")
    if is_ready():
        r_data = get_race(slug)
        if r_data:
            parsed = parse_race_traits(r_data)
            return {
                "text":   format_race_text(r_data),
                "name":   parsed["name"],
                "flavor": parsed["flavor"],
                "traits": parsed["traits"],
            }
    import json as _json, urllib.request as _urlreq
    try:
        req = _urlreq.Request(f"https://api.open5e.com/v1/races/{slug}/",
                              headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            r_data = _json.loads(r.read())
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    parsed = parse_race_traits(r_data)
    return {
        "text":   format_race_text(r_data),
        "name":   parsed["name"],
        "flavor": parsed["flavor"],
        "traits": parsed["traits"],
    }


@router.get("/api/open5e/subclasses")
def open5e_subclasses_proxy(search: str = "", class_slug: str = "", limit: int = 20):
    from ..open5e_local import is_ready, search_subclasses, _source
    cap = min(abs(limit), 100)
    if is_ready():
        items, total = search_subclasses(q=search, class_slug=class_slug, limit=cap)
        return {"count": total, "results": [
            {"name": s.get("name", ""), "slug": s.get("slug", ""),
             "flavor": s.get("subclass_flavor", ""), "source": _source(s)}
            for s in items
        ]}
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
        return {"count": data.get("count", 0), "results": results}
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
            return {"count": len(results), "results": results[:cap]}
        except Exception:
            pass

    # ── Both sources failed — return empty rather than 502 ───────────────────
    return {"count": 0, "results": []}


@router.get("/api/open5e/classes")
def open5e_classes_proxy(search: str = "", limit: int = 20):
    from ..open5e_local import is_ready, search_classes, _source
    cap = min(abs(limit), 30)
    if is_ready():
        items, total = search_classes(q=search, limit=cap)
        return {"count": total, "results": [
            {"name": c.get("name", ""), "slug": c.get("slug", ""),
             "hit_die": c.get("hit_die", ""), "source": _source(c)}
            for c in items
        ]}
    import json as _json, urllib.parse as _urlparse, urllib.request as _urlreq
    url = f"https://api.open5e.com/v1/classes/?{_urlparse.urlencode({'search': search, 'limit': cap})}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    results = []
    for c in data.get("results", []):
        src = c.get("document__title", "") or (
            c.get("document", {}).get("title", "") if isinstance(c.get("document"), dict) else ""
        )
        results.append({"name": c.get("name", ""), "slug": c.get("slug", ""),
                         "hit_die": c.get("hit_die", ""), "source": src})
    return {"count": data.get("count", 0), "results": results}


@router.get("/api/open5e/races")
def open5e_races_proxy(search: str = "", limit: int = 20):
    from ..open5e_local import is_ready, search_races, _source
    cap = min(abs(limit), 30)
    if is_ready():
        items, total = search_races(q=search, limit=cap)
        return {"count": total, "results": [
            {"name": r.get("name", ""), "slug": r.get("slug", ""),
             "size": r.get("size", ""), "source": _source(r)}
            for r in items
        ]}
    import json as _json, urllib.parse as _urlparse, urllib.request as _urlreq
    url = f"https://api.open5e.com/v1/races/?{_urlparse.urlencode({'search': search, 'limit': cap})}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    results = []
    for r in data.get("results", []):
        src = r.get("document__title", "") or (
            r.get("document", {}).get("title", "") if isinstance(r.get("document"), dict) else ""
        )
        results.append({"name": r.get("name", ""), "slug": r.get("slug", ""),
                         "size": r.get("size", ""), "source": src})
    return {"count": data.get("count", 0), "results": results}


@router.get("/api/open5e/spells")
def open5e_spells_proxy(search: str = "", limit: int = 20, spell_list: str = "", level: int = -1):
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
        }

    from ..open5e_local import is_ready, search_spells
    cap = min(abs(limit), 100)
    if is_ready():
        items, total = search_spells(q=search, limit=cap, spell_list=spell_list, level=level)
        return {"count": total, "results": [_fmt_spell(s) for s in items]}
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

    # Ability scores
    for ab, key in [("STR", "strength"), ("DEX", "dexterity"), ("CON", "constitution"),
                    ("INT", "intelligence"), ("WIS", "wisdom"), ("CHA", "charisma")]:
        val = m.get(key)
        if val is not None:
            sheet["abilities"][ab] = int(val)

    # CR → proficiency bonus
    cr_str = str(m.get("challenge_rating", "0"))
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
    sheet["race"] = f"{m.get('size', '')} {m.get('type', '')}".strip()
    sheet["background"] = m.get("alignment", "")

    # Saving throw proficiencies (open5e fields: strength_save etc.)
    for ab, key in [("STR", "strength_save"), ("DEX", "dexterity_save"), ("CON", "constitution_save"),
                    ("INT", "intelligence_save"), ("WIS", "wisdom_save"), ("CHA", "charisma_save")]:
        if m.get(key) is not None:
            sheet["saving_throws"][ab] = True

    # Skill proficiencies
    skill_map = {
        "acrobatics": "Acrobatics", "animal_handling": "Animal Handling", "arcana": "Arcana",
        "athletics": "Athletics", "deception": "Deception", "history": "History",
        "insight": "Insight", "intimidation": "Intimidation", "investigation": "Investigation",
        "medicine": "Medicine", "nature": "Nature", "perception": "Perception",
        "performance": "Performance", "persuasion": "Persuasion", "religion": "Religion",
        "sleight_of_hand": "Sleight of Hand", "stealth": "Stealth", "survival": "Survival",
    }
    for api_key, skill_name in skill_map.items():
        if m.get(api_key) is not None and skill_name in sheet["skills"]:
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

    # Notes: stat block meta
    parts = []
    for label, key in [
        ("Hit Dice", "hit_dice"), ("CR", "challenge_rating"),
        ("Languages", "languages"), ("Senses", "senses"),
        ("Damage Immunities", "damage_immunities"),
        ("Damage Resistances", "damage_resistances"),
        ("Condition Immunities", "condition_immunities"),
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
    return templates.TemplateResponse(tname, {
        "request": request,
        "char": char_obj,
        "sheet": tmpl.sheet or get_template(tmpl.template),
        "can_edit": True,
        "campaign": campaign,
        "sheet_save_url": f"/api/campaign/{campaign_id}/templates/{tmpl_id}",
        "sheet_save_method": "PATCH",
        "portrait_upload_url": f"/api/campaign/{campaign_id}/templates/{tmpl_id}/image",
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
    can_edit = _user_is_gm(user, campaign, db) or char.owner_user_id == user.id
    template_name = "sheet_dnd5e.html" if char.template == "dnd5e" else "sheet_generic.html"
    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "char": char,
            "sheet": char.sheet or get_template(char.template),
            "can_edit": can_edit,
            "campaign": campaign,
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
    if "sheet" in body and isinstance(body["sheet"], dict):
        char.sheet = body["sheet"]
    if "template" in body and body["template"] in ("generic", "dnd5e"):
        char.template = body["template"]
    db.commit()
    await hub.broadcast(
        campaign_id,
        {"type": "character_update", "data": {"id": char.id, "name": char.name}},
    )
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
}


@router.patch("/api/campaign/{campaign_id}/character/{char_id}/sheet-fields")
async def patch_sheet_fields(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Merge a small set of pre-approved keys into a character's sheet JSON."""
    body = await request.json()
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Forbidden")
    patch = {k: v for k, v in body.items() if k in _SHEET_PATCH_KEYS}
    if patch:
        char.sheet = {**(char.sheet or {}), **patch}
        db.commit()
    return {"ok": True}


# ----------- WebSocket -----------

@router.websocket("/ws/campaign/{campaign_id}")
async def campaign_ws(websocket: WebSocket, campaign_id: int):
    session = websocket.session  # type: ignore[attr-defined]
    user_id = session.get("user_id") if session else None
    if not user_id:
        await websocket.close(code=4401)
        return
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not user or not campaign or not _user_can_view_campaign(db, user, campaign):
            await websocket.close(code=4403)
            return
    finally:
        db.close()

    await hub.connect(campaign_id, websocket)
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
    can_edit = _user_is_gm(user, campaign, db) or char.owner_user_id == user.id
    sheet_template = "sheet_dnd5e.html" if char.template == "dnd5e" else "sheet_generic.html"
    return templates.TemplateResponse(
        "character_page.html",
        {
            "request": request,
            "user": user,
            "campaign": campaign,
            "char": char,
            "sheet": char.sheet or get_template(char.template),
            "can_edit": can_edit,
            "sheet_template": sheet_template,
            "system": get_system(campaign.game_system),
        },
    )


# ----------- Settings: characters (GM) -----------

_SETTINGS_UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "static" / "uploads"
_MAP_DIR = _SETTINGS_UPLOAD_ROOT / "maps"
_ALLOWED_IMG = {"image/png", "image/jpeg", "image/webp", "image/gif"}


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
    db.delete(char)
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
    image: UploadFile = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    image_url: Optional[str] = None
    if image and image.filename:
        if image.content_type not in _ALLOWED_IMG:
            raise HTTPException(400, "Unsupported image type")
        data = await image.read()
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(400, "Map image too large (>25 MB)")
        _MAP_DIR.mkdir(parents=True, exist_ok=True)
        ext = Path(image.filename).suffix.lower() or ".png"
        fname = f"{uuid.uuid4().hex}{ext}"
        (_MAP_DIR / fname).write_bytes(data)
        image_url = f"/static/uploads/maps/{fname}"
    try:
        gt = GridType(grid_type)
    except ValueError:
        gt = GridType.SQUARE
    m = Map(
        campaign_id=campaign_id,
        name=name.strip()[:120] or "Map",
        image_url=image_url,
        grid_type=gt,
        grid_size_px=max(20, min(grid_size_px, 300)),
        width_px=max(200, min(width_px, 8000)),
        height_px=max(200, min(height_px, 8000)),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    if not campaign.active_map_id:
        campaign.active_map_id = m.id
        db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#maps", status_code=303)


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
