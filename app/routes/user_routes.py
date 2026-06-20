"""User-facing settings and character pages."""
from __future__ import annotations

import logging
import os
import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..audit_log import audit
from ..auth import require_user
from ..database import get_db
from ..models import (
    AUDIO_CATEGORIES,
    AUDIO_CATEGORY_LABELS,
    Campaign,
    CampaignMembership,
    Character,
    DiceRoll,
    User,
    UserAudioCategoryPref,
    VALID_THEMES,
)
from ..user_export import (
    LAST_EXPORT_MONOTONIC,
    export_cooldown_remaining,
    export_cooldown_seconds,
    iso as _iso,
)
from ..version import APP_VERSION
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


class _SepiaTextureBody(BaseModel):
    enabled: bool


@router.post("/api/settings/sepia_texture")
def update_sepia_texture(
    body: _SepiaTextureBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.84.0 — persist the user's preference for the sepia theme's
    wood-grain background pattern. Default True (on); users who prefer
    the flat solid-color sepia look set False.

    The toggle only takes effect on the sepia theme — the body's
    ``sepia-texture-on`` class is emitted by base.html only when both
    ``user.sepia_texture == True`` AND the active theme is "sepia".
    The CSS selector ``[data-theme="sepia"].sepia-texture-on``
    layers the inline-SVG wood-grain over the existing --bg color.
    """
    user.sepia_texture = bool(body.enabled)
    db.commit()
    return {"ok": True, "sepia_texture": bool(body.enabled)}


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


# ---------------------------------------------------------------------------
# v2.482.0 — GDPR Article 15 (right of access) + Article 20 (data
# portability) self-serve export. Replaces the manual SQL recipe the
# privacy policy (docs/wiki/privacy.md Section 5.1) documented for the
# operator with a logged-in user pulling their own record set as a
# single machine-readable JSON archive. Per Article 20 the format must
# be "structured, commonly used, machine-readable" — JSON satisfies
# that.
# ---------------------------------------------------------------------------

def _test_mode() -> bool:
    return os.environ.get("TEST_MODE", "").strip().lower() in ("1", "true", "yes", "on")


@router.get("/api/users/me/export")
def export_my_data(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GDPR Article 15 / 20 self-serve data export.

    Returns every piece of personal data SimpleVTT holds about the
    authenticated user as a single JSON archive: account fields +
    preferences, campaigns they own, campaign memberships, characters
    they own (full sheet), and dice rolls they authored.

    Deliberately **excludes** the bcrypt ``password_hash`` and the
    Google ``google_sub`` raw value — an access export must not become
    a credential-leak vector. Their presence is surfaced as the
    ``has_password`` / ``has_google_sso`` booleans instead, which is the
    fact a data subject actually needs (which sign-in methods are on
    their account).

    Rate-limited to one export per ``USER_DATA_EXPORT_COOLDOWN_SECONDS``
    (default 24h) per user, bypassed under TEST_MODE so the harness can
    exercise it repeatedly. The 429 path is unit-tested via
    ``app.user_export.export_cooldown_remaining``.
    """
    if not _test_mode():
        remaining = export_cooldown_remaining(
            now=time.monotonic(),
            last_export_at=LAST_EXPORT_MONOTONIC.get(user.id),
            cooldown_seconds=export_cooldown_seconds(),
        )
        if remaining > 0:
            # 429 + Retry-After so a client can back off politely.
            raise HTTPException(
                status_code=429,
                detail=(
                    "Data export was already requested recently. "
                    f"Try again in {remaining} seconds."
                ),
                headers={"Retry-After": str(remaining)},
            )

    campaigns_owned = (
        db.query(Campaign).filter(Campaign.gm_user_id == user.id).all()
    )
    memberships = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.user_id == user.id)
        .all()
    )
    # Resolve membership campaign names in one query (no per-row lookups).
    member_campaign_ids = [m.campaign_id for m in memberships]
    campaign_names: dict[int, str] = {}
    if member_campaign_ids:
        for cid, cname in (
            db.query(Campaign.id, Campaign.name)
            .filter(Campaign.id.in_(member_campaign_ids))
            .all()
        ):
            campaign_names[cid] = cname
    characters = (
        db.query(Character).filter(Character.owner_user_id == user.id).all()
    )
    rolls = (
        db.query(DiceRoll)
        .filter(DiceRoll.user_id == user.id)
        .order_by(DiceRoll.id.asc())
        .all()
    )

    archive = {
        "export_format_version": 1,
        "app_version": APP_VERSION,
        "generated_for_user_id": user.id,
        "note": (
            "GDPR Article 15/20 self-serve export. Contains the personal "
            "data SimpleVTT holds about you. Sensitive credential "
            "material (password hash, Google SSO id) is intentionally "
            "omitted — see has_password / has_google_sso. For the full "
            "data inventory see /wiki/privacy."
        ),
        "account": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": "admin" if user.is_admin else "user",
            "is_disabled": bool(user.is_disabled),
            "has_password": bool(user.password_hash),
            "has_google_sso": bool(user.google_sub),
            "created_at": _iso(user.created_at),
            "preferences": {
                "theme": user.theme,
                "font_preference": user.font_preference,
                "battle_tab_color": user.battle_tab_color,
                "player_tab_color": user.player_tab_color,
                "ui_scale": user.ui_scale,
                "font_scale": user.font_scale,
                "zoom_speed": user.zoom_speed,
                "animate_gifs": bool(user.animate_gifs),
                "roll_log_position": user.roll_log_position,
                "glass_alpha": user.glass_alpha,
                "reaction_prompt_mode": user.reaction_prompt_mode,
                "sepia_texture": bool(user.sepia_texture),
            },
        },
        "campaigns_owned": [
            {"id": c.id, "name": c.name, "created_at": _iso(c.created_at)}
            for c in campaigns_owned
        ],
        "campaign_memberships": [
            {
                "campaign_id": m.campaign_id,
                "campaign_name": campaign_names.get(m.campaign_id),
                "is_gm": bool(m.is_gm),
                "created_at": _iso(m.created_at),
            }
            for m in memberships
        ],
        "characters": [
            {
                "id": ch.id,
                "name": ch.name,
                "campaign_id": ch.campaign_id,
                "template": ch.template,
                "created_at": _iso(ch.created_at),
                "sheet": ch.sheet,
            }
            for ch in characters
        ],
        "dice_rolls": [
            {
                "id": r.id,
                "campaign_id": r.campaign_id,
                "character_id": r.character_id,
                "expression": r.expression,
                "total": r.total,
                "note": r.note,
                "visibility": r.visibility.value
                if hasattr(r.visibility, "value")
                else r.visibility,
                "created_at": _iso(r.created_at),
            }
            for r in rolls
        ],
    }

    if not _test_mode():
        LAST_EXPORT_MONOTONIC[user.id] = time.monotonic()

    # Audit the access so a hijacked-session bulk-dump leaves a trace
    # (the export is a full PII pull; it belongs in the security log).
    audit(
        "user.data_export",
        level=logging.INFO,
        request=request,
        user_id=user.id,
        characters=len(characters),
        rolls=len(rolls),
    )

    # Content-Disposition nudges a browser hitting the URL directly to
    # save the archive as a file rather than render it inline.
    return JSONResponse(
        archive,
        headers={
            "Content-Disposition": (
                f'attachment; filename="simplevtt-export-user-{user.id}.json"'
            ),
        },
    )
