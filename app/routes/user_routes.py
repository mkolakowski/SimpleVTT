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
from ..character_presets import build_sheet as build_preset_sheet
from ..character_presets import list_presets, preset_template
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
            "presets": list_presets(),
        },
    )


def _sheet_for_preset(preset_key: str, fallback_template: str) -> tuple[str, dict]:
    """Resolve a preset key into (template, sheet). Falls back to a blank
    sheet of ``fallback_template`` when the key is unknown or empty."""
    if preset_key:
        built = build_preset_sheet(preset_key)
        if built is not None:
            return preset_template(preset_key), built
    return fallback_template, get_template(fallback_template)


@router.post("/characters/new")
def create_my_character(
    request: Request,
    campaign_id: int = Form(...),
    name: str = Form(...),
    preset: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Player creates their own character in a campaign they belong to.
    Optional ``preset`` field can pre-populate the sheet from
    ``app/character_presets.py``."""
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
    # Resolve preset → sheet/template. Falls back to a blank sheet of the
    # campaign's default game system when no preset (or an unknown one).
    tmpl, sheet = _sheet_for_preset(preset, sys.sheet_template)
    char = Character(
        campaign_id=campaign_id,
        name=name.strip()[:120] or "New Character",
        template=tmpl,
        sheet=sheet,
        owner_user_id=user.id,
    )
    db.add(char)
    db.commit()
    return RedirectResponse("/characters", status_code=303)


@router.post("/characters/new-standalone")
def create_standalone_character(
    name: str = Form(...),
    template: str = Form("generic"),
    preset: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Create a character not tied to any campaign. ``preset`` overrides
    ``template`` when both are supplied (the preset carries its own
    template choice)."""
    from ..game_systems import SYSTEMS
    safe_template = template if template in {s.sheet_template for s in SYSTEMS.values()} else "generic"
    tmpl, sheet = _sheet_for_preset(preset, safe_template)
    char = Character(
        campaign_id=None,
        name=name.strip()[:120] or "New Character",
        template=tmpl,
        sheet=sheet,
        owner_user_id=user.id,
    )
    db.add(char)
    db.commit()
    return RedirectResponse("/characters", status_code=303)


@router.post("/characters/{char_id}/delete")
def delete_my_character(
    char_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Player-initiated character delete. Owner-scoped: a player can only
    delete characters they own. Admins may delete any character (useful when
    a player asks the GM to clean up an old one). Tokens are cascade-cleared
    by the ``ondelete="SET NULL"`` on ``Token.character_id``, so the deletion
    doesn't strand any references on the tabletop side."""
    char = db.query(Character).filter(Character.id == char_id).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if char.owner_user_id != user.id and not user.is_admin:
        raise HTTPException(403, "Not your character")
    db.delete(char)
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
            "is_gm": False,  # standalone characters have no campaign / GM
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
    # Re-use the campaign route's patch helper so subclass writes get routed
    # into the matching ``classes[]`` entry when ``class_slug`` is supplied.
    from .tabletop_routes import _apply_sheet_patch  # local import to avoid cycle
    char.sheet = _apply_sheet_patch(char.sheet, body)
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


class _ZoomSpeedBody(BaseModel):
    zoom_speed: float


def _coerce_zoom_speed(v: float) -> float:
    """Clamp a zoom-speed slider value into [0.3, 1.5]. The slider on
    the user-settings page uses 0.1 steps so any value the GM sends is
    one of {0.3, 0.4, ..., 1.5} — but a hostile client could send
    anything, hence the explicit clamp."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 1.0
    if f != f:  # NaN
        return 1.0
    return max(0.3, min(1.5, f))


@router.post("/api/settings/zoom_speed")
def update_zoom_speed(
    body: _ZoomSpeedBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Persist the user's zoom-speed multiplier. Applied to both wheel
    and pinch on the tabletop canvas; pinch additionally has a
    baked-in 0.6 baseline dampening so the default 1.0 feels right on
    iPad rather than twitchy."""
    user.zoom_speed = _coerce_zoom_speed(body.zoom_speed)
    db.commit()
    return {"ok": True, "zoom_speed": user.zoom_speed}


class _AnimateGifsBody(BaseModel):
    animate_gifs: bool


@router.post("/api/settings/animate_gifs")
def update_animate_gifs(
    body: _AnimateGifsBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Persist the user's preference for animated GIF portraits and tokens."""
    user.animate_gifs = body.animate_gifs
    db.commit()
    return {"ok": True, "animate_gifs": user.animate_gifs}


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


_VALID_ROLL_LOG_POSITIONS = {"left", "right"}


class _RollLogPositionBody(BaseModel):
    position: str


@router.post("/api/settings/roll_log_position")
def update_roll_log_position(
    body: _RollLogPositionBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.49.244 — persist the user's roll-log drawer side preference.
    "right" (default) stacks the panel with the other drawer tabs in
    the shared right sidebar. "left" pulls it into an independent
    left-side sidebar that opens alongside whichever right-side panel
    is active.
    """
    if body.position not in _VALID_ROLL_LOG_POSITIONS:
        raise HTTPException(
            400, f"Invalid position '{body.position}'. "
            f"Valid: {sorted(_VALID_ROLL_LOG_POSITIONS)}",
        )
    user.roll_log_position = body.position
    db.commit()
    return {"ok": True, "roll_log_position": body.position}


class _GlassAlphaBody(BaseModel):
    alpha: int


@router.post("/api/settings/glass_alpha")
def update_glass_alpha(
    body: _GlassAlphaBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.62.0 — persist the user's frosted-glass card transparency.
    Integer percent 1-100. Higher = more opaque (closer to solid
    background); lower = more see-through. Default 42 matches the
    v2.50.3 baseline alpha; the tabletop body element renders the
    value as `--glass-alpha: N%` so the 9 glass-card sites in
    tabletop.html pick it up via `var(--glass-alpha, 42%)`.
    """
    if not isinstance(body.alpha, int):
        raise HTTPException(400, "alpha must be an integer")
    if body.alpha < 1 or body.alpha > 100:
        raise HTTPException(
            400, f"alpha must be in [1, 100]; got {body.alpha}",
        )
    user.glass_alpha = body.alpha
    db.commit()
    return {"ok": True, "glass_alpha": body.alpha}


_VALID_REACTION_PROMPT_MODES = {"popup", "roll_log_only", "off"}


class _ReactionPromptModeBody(BaseModel):
    mode: str


@router.post("/api/settings/reaction_prompt_mode")
def update_reaction_prompt_mode(
    body: _ReactionPromptModeBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.67.1 — persist the user's reaction-prompt UX preference.
    Values:
      "popup"          — popup toast + roll-log entry (default)
      "roll_log_only"  — roll-log entry only (no popup)
      "off"            — no prompts (legacy chip-click only)
    See docs/plans/reactions-automation.md.
    """
    if body.mode not in _VALID_REACTION_PROMPT_MODES:
        raise HTTPException(
            400,
            f"Invalid mode '{body.mode}'. "
            f"Valid: {sorted(_VALID_REACTION_PROMPT_MODES)}",
        )
    user.reaction_prompt_mode = body.mode
    db.commit()
    return {"ok": True, "reaction_prompt_mode": body.mode}
