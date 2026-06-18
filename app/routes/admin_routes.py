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
from .. import local_content, local_features
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
    # v2.425.0 — surface the demo magic-link section only when both
    # gates are open. The runtime check lives in
    # ``demo_magic_link_routes.magic_link_enabled``; importing the
    # predicate here keeps the gate logic in one place.
    from ..demo_magic_link import magic_link_enabled
    from ..demo_seed import DEMO_EMAILS as _DEMO_EMAILS
    from ..integrations.cloudflare import cloudflare_banning_enabled
    from ..models import AdminAuditLog
    cf_enabled = cloudflare_banning_enabled()
    recent_edge_bans = []
    if cf_enabled:
        recent_edge_bans = (
            db.query(AdminAuditLog)
            .filter(AdminAuditLog.action.in_(["cloudflare.ban_ip", "cloudflare.unban_ip"]))
            .order_by(AdminAuditLog.created_at.desc())
            .limit(20)
            .all()
        )
    return templates.TemplateResponse(
        "admin_home.html",
        {
            "request": request,
            "user": user,
            "users": users,
            "campaigns": campaigns,
            "settings": get_settings(),
            "magic_link_enabled": magic_link_enabled(),
            "demo_emails": _DEMO_EMAILS,
            "cloudflare_banning_enabled": cf_enabled,
            "recent_edge_bans": recent_edge_bans,
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


def _enumerate_homebrew(type_dir: str, system: str = "dnd5e") -> list[dict]:
    """Walk every homebrew file across every scope for a given content type.
    Returns each loaded record plus synthetic ``_campaign_id`` (int|None) +
    ``_scope`` (str) + ``_mtime`` keys so callers can build the admin table.
    v2.0.0 audit helper — replaces the per-table SQL joins."""
    out: list[dict] = []
    root = local_content.HOMEBREW_ROOT / system
    if not root.is_dir():
        return out
    model = local_content.TYPE_REGISTRY.get(type_dir)
    if model is None:
        return out
    for scope_dir in sorted(root.iterdir()):
        if not scope_dir.is_dir():
            continue
        scope = scope_dir.name
        cid: int | None = None
        if scope.startswith("campaign-") and scope[9:].isdigit():
            cid = int(scope[9:])
        elif scope != "global":
            continue
        type_path = scope_dir / type_dir
        if not type_path.is_dir():
            continue
        for p in sorted(type_path.iterdir()):
            if not p.name.endswith(".json"):
                continue
            rec = local_content._load_and_validate(p, model)
            if rec is None:
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                mtime = None
            out.append({
                **rec,
                "_campaign_id": cid,
                "_scope": scope,
                "_mtime": mtime,
            })
    return out


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
    # v2.0.0: file-based homebrew audit. The six per-type DB joins are
    # replaced by directory walks against the homebrew volume. Campaign +
    # creator names are resolved in-process; the volumes are small enough
    # that a single batch lookup beats per-record N+1 ORM hits.
    camp_index = {c.id: c.name for c in db.query(Campaign).all()}
    user_index = {u.id: u.display_name for u in db.query(User).all()}

    def _campaign_name(cid: int | None) -> str:
        if cid is None:
            return "(global)"
        return camp_index.get(cid) or f"campaign-{cid}"

    def _creator_name(rec: dict) -> str | None:
        owner = rec.get("owner")
        if isinstance(owner, int):
            return user_index.get(owner)
        return None

    def _ts_fmt(mtime: float | None) -> str:
        if not mtime:
            return ""
        return _dt.datetime.utcfromtimestamp(mtime).strftime("%Y-%m-%d %H:%M UTC")

    def _sort_key(r: dict) -> tuple:
        return (_campaign_name(r["_campaign_id"]), (r.get("name") or "").lower())

    custom_subclasses_db = [
        {
            "id": rec.get("slug"),  # combined "<class>__<sub>"
            "slug": rec.get("slug"),
            "campaign_id": rec["_campaign_id"],
            "campaign_name": _campaign_name(rec["_campaign_id"]),
            "class_slug": (rec.get("slug") or "").partition("__")[0] or (rec.get("class_slug") or ""),
            "sub_slug": (rec.get("slug") or "").partition("__")[2] or (rec.get("slug") or ""),
            "name": rec.get("name"),
            "feature_count": len(rec.get("features") or []) if isinstance(rec.get("features"), list) else 0,
            "created_by": _creator_name(rec),
            "updated_at_fmt": _ts_fmt(rec.get("_mtime")),
        }
        for rec in sorted(_enumerate_homebrew("subclass_features"), key=_sort_key)
    ]

    def _prereq_summary_dict(rec: dict) -> str:
        mca = rec.get("multiclass_prereq_abilities") or {}
        if not mca:
            return "—"
        parts = [f"{k.upper()} {v}" for k, v in mca.items()]
        joiner = " or " if (rec.get("multiclass_prereq_mode") or "all") == "any" else ", "
        return joiner.join(parts)

    custom_classes_db = [
        {
            "id": rec.get("slug"),
            "slug": rec.get("slug"),
            "campaign_id": rec["_campaign_id"],
            "campaign_name": _campaign_name(rec["_campaign_id"]),
            "class_slug": rec.get("slug"),
            "name": rec.get("name"),
            "hit_die": rec.get("hit_die"),
            "spellcasting_ability": rec.get("spellcasting_ability") or "",
            "feature_count": len(rec.get("features") or []) if isinstance(rec.get("features"), list) else 0,
            "spell_count": len(rec.get("spell_list") or []),
            "resource_count": len(rec.get("resources") or []),
            "multiclass_summary": _prereq_summary_dict(rec),
            "created_by": _creator_name(rec),
            "updated_at_fmt": _ts_fmt(rec.get("_mtime")),
        }
        for rec in sorted(_enumerate_homebrew("class_features"), key=_sort_key)
    ]

    def _ab_summary_dict(rec: dict) -> str:
        bonuses = rec.get("ability_bonuses") or []
        if not bonuses:
            return "—"
        return ", ".join(
            f"{(b.get('attribute') or '')[:3].upper()} {'+' if b.get('bonus', 0) >= 0 else ''}{b.get('bonus', 0)}"
            for b in bonuses if isinstance(b, dict)
        )

    custom_races_db = [
        {
            "id": rec.get("slug"),
            "slug": rec.get("slug"),
            "campaign_id": rec["_campaign_id"],
            "campaign_name": _campaign_name(rec["_campaign_id"]),
            "race_slug": rec.get("slug"),
            "name": rec.get("name"),
            "size": rec.get("size") or "—",
            "speed": rec.get("speed"),
            "ability_summary": _ab_summary_dict(rec),
            "trait_count": len(rec.get("traits") or []),
            "created_by": _creator_name(rec),
            "updated_at_fmt": _ts_fmt(rec.get("_mtime")),
        }
        for rec in sorted(_enumerate_homebrew("races"), key=_sort_key)
    ]

    def _action_count(rec: dict) -> int:
        # Unified actions[] with category discriminator at v2.0.0.
        return len(rec.get("actions") or [])

    custom_monsters_db = [
        {
            "id": rec.get("slug"),
            "slug": rec.get("slug"),
            "campaign_id": rec["_campaign_id"],
            "campaign_name": _campaign_name(rec["_campaign_id"]),
            "monster_slug": rec.get("slug"),
            "name": rec.get("name"),
            "size": rec.get("size") or "—",
            "type": rec.get("type") or "—",
            "cr": rec.get("challenge_rating") or "0",
            "ac": rec.get("armor_class"),
            "hp": rec.get("hit_points"),
            "action_count": _action_count(rec),
            "created_by": _creator_name(rec),
            "updated_at_fmt": _ts_fmt(rec.get("_mtime")),
        }
        for rec in sorted(_enumerate_homebrew("monsters"), key=_sort_key)
    ]

    custom_backgrounds_db = [
        {
            "id": rec.get("slug"),
            "slug": rec.get("slug"),
            "campaign_id": rec["_campaign_id"],
            "campaign_name": _campaign_name(rec["_campaign_id"]),
            "background_slug": rec.get("slug"),
            "name": rec.get("name"),
            "feature_name": rec.get("feature_name") or "—",
            "skill_proficiencies": rec.get("skill_proficiencies") or "",
            "created_by": _creator_name(rec),
            "updated_at_fmt": _ts_fmt(rec.get("_mtime")),
        }
        for rec in sorted(_enumerate_homebrew("backgrounds"), key=_sort_key)
    ]

    custom_feats_db = [
        {
            "id": rec.get("slug"),
            "slug": rec.get("slug"),
            "campaign_id": rec["_campaign_id"],
            "campaign_name": _campaign_name(rec["_campaign_id"]),
            "feat_slug": rec.get("slug"),
            "name": rec.get("name"),
            "prerequisite": rec.get("prerequisite") or "—",
            "created_by": _creator_name(rec),
            "updated_at_fmt": _ts_fmt(rec.get("_mtime")),
        }
        for rec in sorted(_enumerate_homebrew("feats"), key=_sort_key)
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


@router.post("/demo/reset")
def admin_demo_reset(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Admin-only on-demand demo reset (v2.3.0). Force-runs
    ``reset_and_reseed`` without waiting for the scheduler's next tick.
    Returns to /admin with the per-section counts on the URL as a hint.
    Returns 503 if DEMO_MODE is disabled."""
    from ..config import get_settings
    s = get_settings()
    if not s.demo_mode:
        raise HTTPException(503, "DEMO_MODE is not enabled on this deploy")
    from ..demo_seed import reset_and_reseed
    counts = reset_and_reseed(db)
    log.info("admin %s triggered demo reset: %s", user.email, counts)
    return {"ok": True, "counts": counts}


@router.get("/stubs.json")
def admin_stubs_json(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """JSON snapshot of the same data the HTML view renders. Useful for
    scripted authoring pipelines (e.g. a script that diffs misses against
    on-disk overrides to suggest the next file to write).

    v2.0.0: all homebrew now lives in per-slug JSON files under the
    homebrew Docker volume; this endpoint walks that volume rather than
    the dropped ``custom_*`` tables.
    """
    def _by_campaign_then_name(r: dict) -> tuple:
        return (r["_campaign_id"] if r["_campaign_id"] is not None else -1, (r.get("name") or "").lower())

    return {
        "local_classes": local_features.list_local_classes(),
        "local_subclasses": local_features.list_local_subclasses(),
        "local_races": local_features.list_local_races(),
        "custom_classes_db": [
            {
                "id": rec.get("slug"),
                "slug": rec.get("slug"),
                "campaign_id": rec["_campaign_id"],
                "class_slug": rec.get("slug"),
                "name": rec.get("name"),
                "hit_die": rec.get("hit_die"),
                "spellcasting_ability": rec.get("spellcasting_ability") or "",
                "feature_count": len(rec.get("features") or []) if isinstance(rec.get("features"), list) else 0,
                "spell_count": len(rec.get("spell_list") or []),
                "resource_count": len(rec.get("resources") or []),
                "multiclass_prereq_abilities": rec.get("multiclass_prereq_abilities") or {},
                "multiclass_prereq_mode": rec.get("multiclass_prereq_mode") or "all",
                "multiclass_proficiencies": rec.get("multiclass_proficiencies") or "",
            }
            for rec in sorted(_enumerate_homebrew("class_features"), key=_by_campaign_then_name)
        ],
        "custom_subclasses_db": [
            {
                "id": rec.get("slug"),
                "slug": rec.get("slug"),
                "campaign_id": rec["_campaign_id"],
                "class_slug": (rec.get("slug") or "").partition("__")[0] or (rec.get("class_slug") or ""),
                "sub_slug": (rec.get("slug") or "").partition("__")[2] or (rec.get("slug") or ""),
                "name": rec.get("name"),
                "feature_count": len(rec.get("features") or []) if isinstance(rec.get("features"), list) else 0,
            }
            for rec in sorted(_enumerate_homebrew("subclass_features"), key=_by_campaign_then_name)
        ],
        "custom_races_db": [
            {
                "id": rec.get("slug"),
                "slug": rec.get("slug"),
                "campaign_id": rec["_campaign_id"],
                "race_slug": rec.get("slug"),
                "name": rec.get("name"),
                "size": rec.get("size") or "",
                "speed": rec.get("speed"),
                "ability_bonuses": rec.get("ability_bonuses") or [],
                "trait_count": len(rec.get("traits") or []),
            }
            for rec in sorted(_enumerate_homebrew("races"), key=_by_campaign_then_name)
        ],
        "custom_monsters_db": [
            {
                "id": rec.get("slug"),
                "slug": rec.get("slug"),
                "campaign_id": rec["_campaign_id"],
                "monster_slug": rec.get("slug"),
                "name": rec.get("name"),
                "size": rec.get("size") or "",
                "type": rec.get("type") or "",
                "cr": rec.get("challenge_rating") or "0",
                "ac": rec.get("armor_class"),
                "hp": rec.get("hit_points"),
                # Per-category counts derived from the unified actions[] list.
                "action_count": sum(1 for a in (rec.get("actions") or []) if (a or {}).get("category") in (None, "", "action")),
                "reaction_count": sum(1 for a in (rec.get("actions") or []) if (a or {}).get("category") == "reaction"),
                "special_count": sum(1 for a in (rec.get("actions") or []) if (a or {}).get("category") == "special_ability"),
                "legendary_count": sum(1 for a in (rec.get("actions") or []) if (a or {}).get("category") == "legendary_action"),
            }
            for rec in sorted(_enumerate_homebrew("monsters"), key=_by_campaign_then_name)
        ],
        "custom_backgrounds_db": [
            {
                "id": rec.get("slug"),
                "slug": rec.get("slug"),
                "campaign_id": rec["_campaign_id"],
                "background_slug": rec.get("slug"),
                "name": rec.get("name"),
                "feature_name": rec.get("feature_name") or "",
                "skill_proficiencies": rec.get("skill_proficiencies") or "",
            }
            for rec in sorted(_enumerate_homebrew("backgrounds"), key=_by_campaign_then_name)
        ],
        "custom_feats_db": [
            {
                "id": rec.get("slug"),
                "slug": rec.get("slug"),
                "campaign_id": rec["_campaign_id"],
                "feat_slug": rec.get("slug"),
                "name": rec.get("name"),
                "prerequisite": rec.get("prerequisite") or "",
            }
            for rec in sorted(_enumerate_homebrew("feats"), key=_by_campaign_then_name)
        ],
        "misses": local_features.list_misses(),
    }
