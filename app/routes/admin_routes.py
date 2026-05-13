"""Admin portal — user/campaign/character management + map upload."""
from __future__ import annotations

import logging
import secrets
import uuid
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
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..auth import hash_password, require_admin
from ..config import get_settings
from ..database import get_db
from ..game_systems import get_system, system_choices
from .. import local_features
from ..models import (
    Campaign,
    CampaignMembership,
    Character,
    CustomBackground,
    CustomClass,
    CustomFeat,
    CustomMonster,
    CustomRace,
    CustomSubclass,
    GridType,
    Map,
    Token,
    User,
)
from ..sheet_templates import get_template
from ..templates import templates

router = APIRouter(prefix="/admin")
log = logging.getLogger(__name__)

UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "static" / "uploads"
MAP_DIR = UPLOAD_ROOT / "maps"
TOKEN_DIR = UPLOAD_ROOT / "tokens"
THUMB_DIR = UPLOAD_ROOT / "thumbnails"
MAP_DIR.mkdir(parents=True, exist_ok=True)
TOKEN_DIR.mkdir(parents=True, exist_ok=True)
THUMB_DIR.mkdir(parents=True, exist_ok=True)


ALLOWED_IMG_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif", "video/webm", "video/mp4"}
MAX_THUMB_BYTES = 5 * 1024 * 1024


async def _save_thumbnail(file: UploadFile) -> str:
    if file.content_type not in ALLOWED_IMG_TYPES:
        raise HTTPException(400, "Unsupported image type")
    data = await file.read()
    if len(data) > MAX_THUMB_BYTES:
        raise HTTPException(400, "Thumbnail too large (>5MB)")
    ext = Path(file.filename).suffix.lower() or ".png"
    fname = f"{uuid.uuid4().hex}{ext}"
    out = THUMB_DIR / fname
    out.write_bytes(data)
    return f"/static/uploads/thumbnails/{fname}"


@router.get("", response_class=HTMLResponse)
def admin_home(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    users = db.query(User).order_by(User.id).all()
    campaigns = db.query(Campaign).order_by(Campaign.id).all()
    return templates.TemplateResponse(
        "admin_home.html",
        {
            "request": request,
            "user": user,
            "users": users,
            "campaigns": campaigns,
            "settings": get_settings(),
        },
    )


# ---------- Users ----------

@router.post("/users")
def admin_create_user(
    email: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    email_n = email.lower().strip()
    if db.query(User).filter(User.email == email_n).first():
        raise HTTPException(400, "Email already in use")
    settings = get_settings()
    u = User(
        email=email_n,
        display_name=display_name.strip() or email_n.split("@")[0],
        password_hash=hash_password(password),
        is_admin=settings.is_admin_email(email_n),
    )
    db.add(u)
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/users/{user_id}/disable")
def admin_disable_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404)
    u.is_disabled = not u.is_disabled
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/users/{user_id}/reset_password")
def admin_reset_password(user_id: int, new_password: str = Form(...), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404)
    if len(new_password) < 8:
        raise HTTPException(400, "Password too short")
    u.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/users/{user_id}/delete")
def admin_delete_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if user_id == user.id:
        raise HTTPException(400, "Can't delete yourself")
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404)
    db.delete(u)
    db.commit()
    return RedirectResponse("/admin", status_code=303)


# ---------- Campaigns ----------

@router.get("/campaign/{campaign_id}", response_class=HTMLResponse)
def admin_campaign(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404)
    member_rows = (
        db.query(CampaignMembership, User)
        .join(User, User.id == CampaignMembership.user_id)
        .filter(CampaignMembership.campaign_id == campaign_id)
        .all()
    )
    members = [u for _m, u in member_rows]
    members_with_role = [
        {"user": u, "is_gm": m.is_gm, "membership_id": m.id} for m, u in member_rows
    ]
    non_members = (
        db.query(User)
        .filter(
            ~User.id.in_(
                db.query(CampaignMembership.user_id).filter(
                    CampaignMembership.campaign_id == campaign_id
                )
            )
        )
        .filter(User.id != campaign.gm_user_id)
        .all()
    )
    characters = db.query(Character).filter(Character.campaign_id == campaign_id).all()
    maps = db.query(Map).filter(Map.campaign_id == campaign_id).all()
    return templates.TemplateResponse(
        "admin_campaign.html",
        {
            "request": request,
            "user": user,
            "campaign": campaign,
            "members": members,
            "non_members": non_members,
            "characters": characters,
            "maps": maps,
            "all_users": db.query(User).all(),
            "system_choices": system_choices(),
            "current_system": get_system(campaign.game_system),
            "members_with_role": members_with_role,
        },
    )


@router.post("/campaign/{campaign_id}/members/add")
def admin_add_member(campaign_id: int, user_id: int = Form(...), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if not db.query(Campaign).filter(Campaign.id == campaign_id).first():
        raise HTTPException(404)
    existing = (
        db.query(CampaignMembership)
        .filter(
            CampaignMembership.campaign_id == campaign_id,
            CampaignMembership.user_id == user_id,
        )
        .first()
    )
    if not existing:
        db.add(CampaignMembership(campaign_id=campaign_id, user_id=user_id))
        db.commit()
    return RedirectResponse(f"/admin/campaign/{campaign_id}", status_code=303)


@router.post("/campaign/{campaign_id}/members/remove")
def admin_remove_member(campaign_id: int, user_id: int = Form(...), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    db.query(CampaignMembership).filter(
        CampaignMembership.campaign_id == campaign_id,
        CampaignMembership.user_id == user_id,
    ).delete()
    db.commit()
    return RedirectResponse(f"/admin/campaign/{campaign_id}", status_code=303)


@router.post("/campaign/{campaign_id}/characters")
def admin_create_character(
    campaign_id: int,
    name: str = Form(...),
    owner_user_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Create a character. Template is forced to the campaign's locked system."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404)
    sys = get_system(campaign.game_system)
    char = Character(
        campaign_id=campaign_id,
        name=name.strip()[:120] or "New character",
        template=sys.sheet_template,
        sheet=get_template(sys.sheet_template),
        owner_user_id=owner_user_id if owner_user_id else None,
    )
    db.add(char)
    db.commit()
    return RedirectResponse(f"/admin/campaign/{campaign_id}", status_code=303)


@router.post("/campaign/{campaign_id}/system")
async def admin_update_campaign_system(campaign_id: int, game_system: str = Form(...), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404)
    campaign.game_system = get_system(game_system).key
    db.commit()
    return RedirectResponse(f"/admin/campaign/{campaign_id}", status_code=303)


@router.post("/campaign/{campaign_id}/thumbnail")
async def admin_upload_thumbnail(campaign_id: int, thumbnail: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404)
    campaign.thumbnail_url = await _save_thumbnail(thumbnail)
    db.commit()
    return RedirectResponse(f"/admin/campaign/{campaign_id}", status_code=303)


@router.post("/campaign/{campaign_id}/thumbnail/clear")
async def admin_clear_thumbnail(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404)
    campaign.thumbnail_url = None
    db.commit()
    return RedirectResponse(f"/admin/campaign/{campaign_id}", status_code=303)


@router.post("/campaign/{campaign_id}/characters/{char_id}/assign")
def admin_assign_character(campaign_id: int, char_id: int, owner_user_id: Optional[int] = Form(None), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    char = db.query(Character).filter(Character.id == char_id).first()
    if not char or char.campaign_id != campaign_id:
        raise HTTPException(404)
    char.owner_user_id = owner_user_id if owner_user_id else None
    db.commit()
    return RedirectResponse(f"/admin/campaign/{campaign_id}", status_code=303)


@router.post("/campaign/{campaign_id}/characters/{char_id}/delete")
def admin_delete_character(campaign_id: int, char_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    char = db.query(Character).filter(Character.id == char_id).first()
    if not char or char.campaign_id != campaign_id:
        raise HTTPException(404)
    db.delete(char)
    db.commit()
    return RedirectResponse(f"/admin/campaign/{campaign_id}", status_code=303)


# ---------- Maps ----------

@router.post("/campaign/{campaign_id}/maps")
async def admin_upload_map(
    campaign_id: int,
    name: str = Form(...),
    grid_type: str = Form("square"),
    grid_size_px: int = Form(70),
    width_px: int = Form(2000),
    height_px: int = Form(1500),
    image: UploadFile = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404)
    image_url: Optional[str] = None
    if image and image.filename:
        if image.content_type not in ALLOWED_IMG_TYPES:
            raise HTTPException(400, "Unsupported image type")
        ext = Path(image.filename).suffix.lower() or ".png"
        fname = f"{uuid.uuid4().hex}{ext}"
        out = MAP_DIR / fname
        data = await image.read()
        if len(data) > 80 * 1024 * 1024:
            raise HTTPException(400, "Map image too large (>80 MB)")
        out.write_bytes(data)
        image_url = f"/static/uploads/maps/{fname}"
        if image.content_type and image.content_type.startswith("image/"):
            try:
                import io as _io
                from PIL import Image as _PILImage
                with _PILImage.open(_io.BytesIO(data)) as _img:
                    width_px, height_px = _img.size
            except Exception:
                pass
    try:
        gt = GridType(grid_type)
    except ValueError:
        gt = GridType.SQUARE
    m = Map(
        campaign_id=campaign_id,
        name=name.strip()[:120] or "Map",
        image_url=image_url,
        grid_type=gt,
        grid_size_px=max(20, min(int(grid_size_px), 300)),
        width_px=max(200, min(int(width_px), 8000)),
        height_px=max(200, min(int(height_px), 8000)),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    if not campaign.active_map_id:
        campaign.active_map_id = m.id
        db.commit()
    return RedirectResponse(f"/admin/campaign/{campaign_id}", status_code=303)


@router.post("/campaign/{campaign_id}/maps/{map_id}/activate")
def admin_activate_map(campaign_id: int, map_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    m = db.query(Map).filter(Map.id == map_id).first()
    if not campaign or not m or m.campaign_id != campaign_id:
        raise HTTPException(404)
    campaign.active_map_id = m.id
    db.commit()
    return RedirectResponse(f"/admin/campaign/{campaign_id}", status_code=303)


@router.post("/campaign/{campaign_id}/delete")
def admin_delete_campaign(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404)
    c.active_map_id = None
    db.commit()
    db.delete(c)
    db.commit()
    return RedirectResponse("/admin", status_code=303)


# ---------- Local-features stubs panel ----------
#
# Surfaces (a) what's currently authored as local overrides and (b) the
# in-memory miss registry — class / subclass lookups that fell through to
# Open5e since the process started.  Lets an operator see, sorted by hit
# count, which content is worth promoting to a local file next.

import datetime as _dt


def _fmt_ts(ts: float | None) -> str:
    if not ts:
        return ""
    return _dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M UTC")


@router.get("/stubs", response_class=HTMLResponse)
def admin_stubs(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    misses_raw = local_features.list_misses()
    misses = [
        {
            **m,
            "first_seen_fmt": _fmt_ts(m.get("first_seen")),
            "last_seen_fmt": _fmt_ts(m.get("last_seen")),
        }
        for m in misses_raw
    ]
    # DB-backed homebrew (CustomSubclass rows) — campaign-scoped overrides
    # authored via the GM settings form. Joined to Campaign so the table
    # can show "which campaign" and "by whom" without N+1 lookups in the
    # template.
    custom_rows = (
        db.query(CustomSubclass, Campaign, User)
        .join(Campaign, Campaign.id == CustomSubclass.campaign_id)
        .outerjoin(User, User.id == CustomSubclass.created_by_user_id)
        .order_by(Campaign.name, CustomSubclass.class_slug, CustomSubclass.name)
        .all()
    )
    custom_subclasses_db = [
        {
            "id": cs.id,
            "campaign_id": cs.campaign_id,
            "campaign_name": camp.name,
            "class_slug": cs.class_slug,
            "sub_slug": cs.sub_slug,
            "name": cs.name,
            "feature_count": len(cs.features or []),
            "created_by": creator.display_name if creator else None,
            "updated_at_fmt": cs.updated_at.strftime("%Y-%m-%d %H:%M UTC") if cs.updated_at else "",
        }
        for cs, camp, creator in custom_rows
    ]
    custom_class_rows = (
        db.query(CustomClass, Campaign, User)
        .join(Campaign, Campaign.id == CustomClass.campaign_id)
        .outerjoin(User, User.id == CustomClass.created_by_user_id)
        .order_by(Campaign.name, CustomClass.name)
        .all()
    )
    def _prereq_summary(cc) -> str:
        mca = cc.multiclass_prereq_abilities or {}
        if not mca:
            return "—"
        parts = [f"{k.upper()} {v}" for k, v in mca.items()]
        joiner = " or " if (cc.multiclass_prereq_mode or "all") == "any" else ", "
        return joiner.join(parts)

    custom_classes_db = [
        {
            "id": cc.id,
            "campaign_id": cc.campaign_id,
            "campaign_name": camp.name,
            "class_slug": cc.class_slug,
            "name": cc.name,
            "hit_die": cc.hit_die,
            "spellcasting_ability": cc.spellcasting_ability or "",
            "feature_count": len(cc.features or []),
            "spell_count": len(cc.spell_list or []),
            "resource_count": len(cc.resources or []),
            "multiclass_summary": _prereq_summary(cc),
            "created_by": creator.display_name if creator else None,
            "updated_at_fmt": cc.updated_at.strftime("%Y-%m-%d %H:%M UTC") if cc.updated_at else "",
        }
        for cc, camp, creator in custom_class_rows
    ]
    custom_race_rows = (
        db.query(CustomRace, Campaign, User)
        .join(Campaign, Campaign.id == CustomRace.campaign_id)
        .outerjoin(User, User.id == CustomRace.created_by_user_id)
        .order_by(Campaign.name, CustomRace.name)
        .all()
    )

    def _ab_summary(cr) -> str:
        bonuses = cr.ability_bonuses or []
        if not bonuses:
            return "—"
        return ", ".join(
            f"{(b.get('attribute') or '')[:3].upper()} {'+' if b.get('bonus', 0) >= 0 else ''}{b.get('bonus', 0)}"
            for b in bonuses if isinstance(b, dict)
        )

    custom_races_db = [
        {
            "id": cr.id,
            "campaign_id": cr.campaign_id,
            "campaign_name": camp.name,
            "race_slug": cr.race_slug,
            "name": cr.name,
            "size": cr.size or "—",
            "speed": cr.speed,
            "ability_summary": _ab_summary(cr),
            "trait_count": len(cr.traits or []),
            "created_by": creator.display_name if creator else None,
            "updated_at_fmt": cr.updated_at.strftime("%Y-%m-%d %H:%M UTC") if cr.updated_at else "",
        }
        for cr, camp, creator in custom_race_rows
    ]

    custom_monster_rows = (
        db.query(CustomMonster, Campaign, User)
        .join(Campaign, Campaign.id == CustomMonster.campaign_id)
        .outerjoin(User, User.id == CustomMonster.created_by_user_id)
        .order_by(Campaign.name, CustomMonster.name)
        .all()
    )

    custom_monsters_db = [
        {
            "id": cm.id,
            "campaign_id": cm.campaign_id,
            "campaign_name": camp.name,
            "monster_slug": cm.monster_slug,
            "name": cm.name,
            "size": cm.size or "—",
            "type": cm.type or "—",
            "cr": cm.challenge_rating or "0",
            "ac": cm.armor_class,
            "hp": cm.hit_points,
            "action_count": len(cm.actions or []) + len(cm.reactions or []) + len(cm.special_abilities or []) + len(cm.legendary_actions or []),
            "created_by": creator.display_name if creator else None,
            "updated_at_fmt": cm.updated_at.strftime("%Y-%m-%d %H:%M UTC") if cm.updated_at else "",
        }
        for cm, camp, creator in custom_monster_rows
    ]

    custom_background_rows = (
        db.query(CustomBackground, Campaign, User)
        .join(Campaign, Campaign.id == CustomBackground.campaign_id)
        .outerjoin(User, User.id == CustomBackground.created_by_user_id)
        .order_by(Campaign.name, CustomBackground.name)
        .all()
    )
    custom_backgrounds_db = [
        {
            "id": cb.id,
            "campaign_id": cb.campaign_id,
            "campaign_name": camp.name,
            "background_slug": cb.background_slug,
            "name": cb.name,
            "feature_name": cb.feature_name or "—",
            "skill_proficiencies": cb.skill_proficiencies or "",
            "created_by": creator.display_name if creator else None,
            "updated_at_fmt": cb.updated_at.strftime("%Y-%m-%d %H:%M UTC") if cb.updated_at else "",
        }
        for cb, camp, creator in custom_background_rows
    ]
    custom_feat_rows = (
        db.query(CustomFeat, Campaign, User)
        .join(Campaign, Campaign.id == CustomFeat.campaign_id)
        .outerjoin(User, User.id == CustomFeat.created_by_user_id)
        .order_by(Campaign.name, CustomFeat.name)
        .all()
    )
    custom_feats_db = [
        {
            "id": cf.id,
            "campaign_id": cf.campaign_id,
            "campaign_name": camp.name,
            "feat_slug": cf.feat_slug,
            "name": cf.name,
            "prerequisite": cf.prerequisite or "—",
            "created_by": creator.display_name if creator else None,
            "updated_at_fmt": cf.updated_at.strftime("%Y-%m-%d %H:%M UTC") if cf.updated_at else "",
        }
        for cf, camp, creator in custom_feat_rows
    ]

    return templates.TemplateResponse(
        "admin_stubs.html",
        {
            "request": request,
            "user": user,
            "local_classes": local_features.list_local_classes(),
            "local_subclasses": local_features.list_local_subclasses(),
            "local_races": local_features.list_local_races(),
            "custom_classes_db": custom_classes_db,
            "custom_subclasses_db": custom_subclasses_db,
            "custom_races_db": custom_races_db,
            "custom_monsters_db": custom_monsters_db,
            "custom_backgrounds_db": custom_backgrounds_db,
            "custom_feats_db": custom_feats_db,
            "misses": misses,
        },
    )


@router.post("/stubs/clear")
def admin_stubs_clear(user: User = Depends(require_admin)):
    local_features.clear_misses()
    return RedirectResponse("/admin/stubs", status_code=303)


@router.get("/stubs.json")
def admin_stubs_json(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """JSON snapshot of the same data the HTML view renders. Useful for
    scripted authoring pipelines (e.g. a script that diffs misses against
    on-disk overrides to suggest the next file to write)."""
    return {
        "local_classes": local_features.list_local_classes(),
        "local_subclasses": local_features.list_local_subclasses(),
        "local_races": local_features.list_local_races(),
        "custom_classes_db": [
            {
                "id": cc.id,
                "campaign_id": cc.campaign_id,
                "class_slug": cc.class_slug,
                "name": cc.name,
                "hit_die": cc.hit_die,
                "spellcasting_ability": cc.spellcasting_ability or "",
                "feature_count": len(cc.features or []),
                "spell_count": len(cc.spell_list or []),
                "resource_count": len(cc.resources or []),
                "multiclass_prereq_abilities": cc.multiclass_prereq_abilities or {},
                "multiclass_prereq_mode": cc.multiclass_prereq_mode or "all",
                "multiclass_proficiencies": cc.multiclass_proficiencies or "",
            }
            for cc in db.query(CustomClass).order_by(CustomClass.campaign_id, CustomClass.name).all()
        ],
        "custom_subclasses_db": [
            {
                "id": cs.id,
                "campaign_id": cs.campaign_id,
                "class_slug": cs.class_slug,
                "sub_slug": cs.sub_slug,
                "name": cs.name,
                "feature_count": len(cs.features or []),
            }
            for cs in db.query(CustomSubclass).order_by(CustomSubclass.campaign_id, CustomSubclass.name).all()
        ],
        "custom_races_db": [
            {
                "id": cr.id,
                "campaign_id": cr.campaign_id,
                "race_slug": cr.race_slug,
                "name": cr.name,
                "size": cr.size or "",
                "speed": cr.speed,
                "ability_bonuses": cr.ability_bonuses or [],
                "trait_count": len(cr.traits or []),
            }
            for cr in db.query(CustomRace).order_by(CustomRace.campaign_id, CustomRace.name).all()
        ],
        "custom_monsters_db": [
            {
                "id": cm.id,
                "campaign_id": cm.campaign_id,
                "monster_slug": cm.monster_slug,
                "name": cm.name,
                "size": cm.size or "",
                "type": cm.type or "",
                "cr": cm.challenge_rating or "0",
                "ac": cm.armor_class,
                "hp": cm.hit_points,
                "action_count": len(cm.actions or []),
                "reaction_count": len(cm.reactions or []),
                "special_count": len(cm.special_abilities or []),
                "legendary_count": len(cm.legendary_actions or []),
            }
            for cm in db.query(CustomMonster).order_by(CustomMonster.campaign_id, CustomMonster.name).all()
        ],
        "custom_backgrounds_db": [
            {
                "id": cb.id,
                "campaign_id": cb.campaign_id,
                "background_slug": cb.background_slug,
                "name": cb.name,
                "feature_name": cb.feature_name or "",
                "skill_proficiencies": cb.skill_proficiencies or "",
            }
            for cb in db.query(CustomBackground).order_by(CustomBackground.campaign_id, CustomBackground.name).all()
        ],
        "custom_feats_db": [
            {
                "id": cf.id,
                "campaign_id": cf.campaign_id,
                "feat_slug": cf.feat_slug,
                "name": cf.name,
                "prerequisite": cf.prerequisite or "",
            }
            for cf in db.query(CustomFeat).order_by(CustomFeat.campaign_id, CustomFeat.name).all()
        ],
        "misses": local_features.list_misses(),
    }
