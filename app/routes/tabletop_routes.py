"""Tabletop pages + REST/WebSocket APIs.

REST is used for state-changing actions (move token, roll dice, edit sheet).
The WebSocket pushes those changes to other connected clients.
"""
from __future__ import annotations

import logging
from datetime import timezone
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
    DiceRoll,
    Map,
    Playlist,
    PlaylistTrack,
    Token,
    User,
    Visibility,
)
from ..realtime import hub
from ..sheet_templates import get_template
from ..templates import templates

router = APIRouter()
log = logging.getLogger(__name__)


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
        {"user": u, "is_gm": m.is_gm, "membership_id": m.id} for m, u in member_rows
    ]
    primary_gm = db.query(User).filter(User.id == campaign.gm_user_id).first()
    playlists = (
        db.query(Playlist)
        .filter(Playlist.campaign_id == campaign_id)
        .order_by(Playlist.id)
        .all()
    )
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
            "playlists": playlists,
        },
    )


@router.post("/campaign/{campaign_id}/settings")
async def campaign_settings_save(
    campaign_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    game_system: str = Form("generic"),
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
    return templates.TemplateResponse(
        "rolls_popout.html",
        {
            "request": request,
            "user": user,
            "campaign": campaign,
            "rolls": visible,
            "is_gm": _user_is_gm(user, campaign, db),
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
    t = Token(
        map_id=campaign.active_map_id,
        character_id=body.get("character_id"),
        label=str(body.get("label", "Token"))[:120],
        color=str(body.get("color", "#cc3333"))[:20],
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


def _token_dict(t: Token) -> dict:
    return {
        "id": t.id,
        "label": t.label,
        "color": t.color,
        "x": t.x,
        "y": t.y,
        "size": t.size,
        "character_id": t.character_id,
        "image_url": t.image_url,
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
    await hub.broadcast(
        campaign_id,
        {
            "type": "roll",
            "data": {
                "id": rec.id,
                "user_id": user.id,
                "user_name": user.display_name,
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
aign,
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
