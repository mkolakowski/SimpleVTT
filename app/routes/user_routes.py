"""User-facing settings and character pages."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_user
from ..database import get_db
from ..models import (
    AUDIO_CATEGORIES,
    AUDIO_CATEGORY_LABELS,
    Campaign,
    CampaignMembership,
    Character,
    User,
    UserAudioCategoryPref,
    VALID_THEMES,
)
from ..game_systems import get_system
from ..sheet_templates import get_template
from ..templates import templates

router = APIRouter()


@router.get("/characters", response_class=HTMLResponse)
def all_characters(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """All characters owned by this user, grouped by campaign."""
    chars = (
        db.query(Character, Campaign)
        .outerjoin(Campaign, Campaign.id == Character.campaign_id)
        .filter(Character.owner_user_id == user.id)
        .order_by(Campaign.name, Character.name)
        .all()
    )
    # Group by campaign; None campaign_id goes into a standalone bucket
    grouped: list[dict] = []
    seen: dict[int | None, dict] = {}
    standalone: list[Character] = []
    for char, campaign in chars:
        if campaign is None:
            standalone.append(char)
        else:
            if campaign.id not in seen:
                entry = {"campaign": campaign, "system": get_system(campaign.game_system), "characters": []}
                seen[campaign.id] = entry
                grouped.append(entry)
            seen[campaign.id]["characters"].append(char)

    # Campaigns this user can create characters in (member or GM)
    member_campaign_ids = {
        m.campaign_id for m in
        db.query(CampaignMembership).filter(CampaignMembership.user_id == user.id).all()
    }
    gm_campaigns = db.query(Campaign).filter(Campaign.gm_user_id == user.id).all()
    gm_campaign_ids = {c.id for c in gm_campaigns}
    all_member_campaign_ids = member_campaign_ids | gm_campaign_ids
    member_campaigns = (
        db.query(Campaign)
        .filter(Campaign.id.in_(all_member_campaign_ids))
        .order_by(Campaign.name)
        .all()
    ) if all_member_campaign_ids else []

    return templates.TemplateResponse(
        "all_characters.html",
        {
            "request": request,
            "user": user,
            "grouped": grouped,
            "standalone": standalone,
            "member_campaigns": member_campaigns,
        },
    )


@router.post("/characters/new")
def create_my_character(
    request: Request,
    campaign_id: int = Form(...),
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Player creates their own character in a campaign they belong to."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        from fastapi import HTTPException
        raise HTTPException(404, "Campaign not found")
    is_member = (
        campaign.gm_user_id == user.id
        or db.query(CampaignMembership).filter(
            CampaignMembership.campaign_id == campaign_id,
            CampaignMembership.user_id == user.id,
        ).first() is not None
        or user.is_admin
    )
    if not is_member:
        raise HTTPException(403, "Not a member of this campaign")
    sys = get_system(campaign.game_system)
    char = Character(
        campaign_id=campaign_id,
        name=name.strip()[:120] or "New Character",
        template=sys.sheet_template,
        sheet=get_template(sys.sheet_template),
        owner_user_id=user.id,
    )
    db.add(char)
    db.commit()
    return RedirectResponse("/characters", status_code=303)


@router.post("/characters/new-standalone")
def create_standalone_character(
    name: str = Form(...),
    template: str = Form("generic"),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Create a character not tied to any campaign."""
    from ..game_systems import SYSTEMS
    safe_template = template if template in {s.sheet_template for s in SYSTEMS.values()} else "generic"
    char = Character(
        campaign_id=None,
        name=name.strip()[:120] or "New Character",
        template=safe_template,
        sheet=get_template(safe_template),
        owner_user_id=user.id,
    )
    db.add(char)
    db.commit()
    return RedirectResponse("/characters", status_code=303)


@router.get("/character/{char_id}/sheet", response_class=HTMLResponse)
def standalone_character_sheet(
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Full-page sheet for a standalone (campaign-less) character."""
    char = db.query(Character).filter(Character.id == char_id).first()
    if not char or char.campaign_id is not None:
        raise HTTPException(404, "Not found")
    if char.owner_user_id != user.id and not user.is_admin:
        raise HTTPException(403, "Not your character")
    sheet_template = "sheet_dnd5e.html" if char.template == "dnd5e" else "sheet_generic.html"
    return templates.TemplateResponse(
        "character_page.html",
        {
            "request": request,
            "user": user,
            "campaign": None,
            "char": char,
            "sheet": char.sheet or get_template(char.template),
            "can_edit": True,
            "sheet_template": sheet_template,
        },
    )


@router.post("/api/character/{char_id}")
async def update_standalone_sheet(
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Save sheet data for a standalone character."""
    char = db.query(Character).filter(Character.id == char_id).first()
    if not char or char.campaign_id is not None:
        raise HTTPException(404)
    if char.owner_user_id != user.id and not user.is_admin:
        raise HTTPException(403)
    body = await request.json()
    if "name" in body:
        char.name = str(body["name"]).strip()[:120] or char.name
    if "sheet" in body:
        char.sheet = body["sheet"]
    db.commit()
    return JSONResponse({"ok": True})


_SHEET_PATCH_KEYS = {
    # Subclass features (new per-feature format + legacy blob)
    "subclass_features_data",
    "subclass_name",
    "subclass_flavor",
    "subclass_features",        # list[{name, desc, level}]
    # Race traits (same pattern)
    "race_parsed_data",
    "race_flavor",
    "race_trait_items",         # list[{name, desc}]
}


@router.patch("/api/character/{char_id}/sheet-fields")
async def patch_standalone_sheet_fields(
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Merge a small set of pre-approved keys into a standalone character's sheet JSON."""
    char = db.query(Character).filter(Character.id == char_id).first()
    if not char or char.campaign_id is not None:
        raise HTTPException(404)
    if char.owner_user_id != user.id and not user.is_admin:
        raise HTTPException(403)
    body = await request.json()
    patch = {k: v for k, v in body.items() if k in _SHEET_PATCH_KEYS}
    if patch:
        char.sheet = {**(char.sheet or {}), **patch}
        db.commit()
    return JSONResponse({"ok": True})


@router.get("/settings", response_class=HTMLResponse)
def user_settings(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Show per-category audio volume preferences and theme setting for this user."""
    prefs = {
        p.category: p.volume
        for p in db.query(UserAudioCategoryPref)
        .filter(UserAudioCategoryPref.user_id == user.id)
        .all()
    }
    categories = [
        {"key": cat, "label": AUDIO_CATEGORY_LABELS[cat], "volume": prefs.get(cat, 1.0)}
        for cat in AUDIO_CATEGORIES
    ]
    return templates.TemplateResponse(
        "user_settings.html",
        {
            "request": request,
            "user": user,
            "categories": categories,
        },
    )


class _ThemeBody(BaseModel):
    theme: str


@router.post("/api/settings/theme")
def update_theme(
    body: _ThemeBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Persist the user's chosen UI theme to their account."""
    if body.theme not in VALID_THEMES:
        raise HTTPException(400, f"Invalid theme '{body.theme}'. Valid: {sorted(VALID_THEMES)}")
    user.theme = body.theme
    db.commit()
    return {"ok": True, "theme": body.theme}


_VALID_FONTS = {"", "lora", "cormorant", "im-fell"}


class _FontBody(BaseModel):
    font: str


@router.post("/api/settings/font")
def update_font(
    body: _FontBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Persist the user's chosen display font preference."""
    if body.font not in _VALID_FONTS:
        raise HTTPException(400, f"Invalid font '{body.font}'. Valid: {sorted(_VALID_FONTS)}")
    user.font_preference = body.font or None
    db.commit()
    return {"ok": True, "font": body.font}


class _TabColorBody(BaseModel):
    key: str   # "battle" | "player"
    color: str  # hex color string, or "" to clear


_VALID_TAB_COLOR_KEYS = {"battle", "player"}


# Allowed scale factors. Constrain server-side so a malicious client can't
# DoS themselves by setting a 0 or 50× scale.
_VALID_SCALES = (0.75, 0.85, 0.90, 1.00, 1.10, 1.25, 1.50)


def _coerce_scale(v: float) -> float:
    """Snap an incoming scale value to the closest allowed preset."""
    return min(_VALID_SCALES, key=lambda s: abs(s - float(v)))


class _ScaleBody(BaseModel):
    ui_scale: float | None = None
    font_scale: float | None = None


@router.post("/api/settings/scale")
def update_scale(
    body: _ScaleBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Persist the user's chosen UI / font scale presets."""
    if body.ui_scale is not None:
        user.ui_scale = _coerce_scale(body.ui_scale)
    if body.font_scale is not None:
        user.font_scale = _coerce_scale(body.font_scale)
    db.commit()
    return {"ok": True, "ui_scale": user.ui_scale, "font_scale": user.font_scale}


@router.post("/api/settings/tab_color")
def update_tab_color(
    body: _TabColorBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Persist a per-user sidebar tab tint color."""
    if body.key not in _VALID_TAB_COLOR_KEYS:
        raise HTTPException(400, f"Invalid tab key '{body.key}'")
    color = body.color.strip()[:20] or None
    if body.key == "battle":
        user.battle_tab_color = color
    elif body.key == "player":
        user.player_tab_color = color
    db.commit()
    return {"ok": True}
