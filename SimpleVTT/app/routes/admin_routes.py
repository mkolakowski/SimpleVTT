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
from ..models import (
    Campaign,
    CampaignMembership,
    Character,
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


ALLOWED_IMG_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
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
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(400, "Map image too large (>25MB)")
        out.write_bytes(data)
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
