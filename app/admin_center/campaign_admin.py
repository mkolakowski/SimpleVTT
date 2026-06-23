"""Campaign-administration service functions for the Admin Center.

Phase 3 of ``docs/plans/admin-center-consolidation.md`` moves the
site-admin **campaign management** out of the main app's in-app
``/admin`` portal into the Center. Phase 3a (this module's wired
callers): browse — a campaign list + a read-only detail view — plus the
headline destructive action, **delete campaign** (MFA-gated by the
route). Member / character / map / system management (incl. file
uploads) is a later 3b.

Like ``user_admin``, these are dependency-light service functions free of
FastAPI / auth concerns: the Center route owns the
``ADMIN_CENTER_ADMIN_TOOLS`` gate, the MFA gate on delete, and the
operator-audit emission. Validation/precondition failures raise
``CampaignAdminError``.
"""
from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from ..models import Campaign, CampaignMembership, Character, Map, User


class CampaignAdminError(Exception):
    """A validation/precondition failure the route surfaces to the operator."""


def list_campaigns(db: Session) -> List[dict]:
    """All campaigns, id-ordered, each with its GM email + member/character/
    map counts for the list view (counted in Python from small per-campaign
    queries — the operator box has a handful of campaigns, not millions)."""
    rows: List[dict] = []
    for c in db.query(Campaign).order_by(Campaign.id).all():
        gm = db.query(User).filter(User.id == c.gm_user_id).first()
        rows.append({
            "id": c.id,
            "name": c.name,
            "game_system": c.game_system,
            "gm_email": gm.email if gm else f"<user {c.gm_user_id}>",
            "members": db.query(CampaignMembership)
                         .filter(CampaignMembership.campaign_id == c.id).count(),
            "characters": db.query(Character)
                            .filter(Character.campaign_id == c.id).count(),
            "maps": db.query(Map).filter(Map.campaign_id == c.id).count(),
        })
    return rows


def get_campaign_detail(db: Session, campaign_id: int) -> dict:
    """The read-only detail bundle: the campaign, its members (with role),
    characters, and maps. Raises CampaignAdminError when unknown."""
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise CampaignAdminError(f"No campaign with id {campaign_id}")
    member_rows = (
        db.query(CampaignMembership, User)
        .join(User, User.id == CampaignMembership.user_id)
        .filter(CampaignMembership.campaign_id == campaign_id)
        .all()
    )
    members = [
        {"user_id": u.id, "email": u.email, "display_name": u.display_name, "is_gm": m.is_gm}
        for m, u in member_rows
    ]
    gm = db.query(User).filter(User.id == c.gm_user_id).first()
    characters = (
        db.query(Character).filter(Character.campaign_id == campaign_id)
        .order_by(Character.id).all()
    )
    maps = (
        db.query(Map).filter(Map.campaign_id == campaign_id)
        .order_by(Map.id).all()
    )
    # Phase 3b management inputs: users not yet a member (for the add-member
    # dropdown, excluding the GM who is implicitly attached) + all users (for
    # character ownership) + the system choices.
    member_ids = {
        uid for (uid,) in db.query(CampaignMembership.user_id)
        .filter(CampaignMembership.campaign_id == campaign_id).all()
    }
    non_members = [
        u for u in db.query(User).order_by(User.id).all()
        if u.id not in member_ids and u.id != c.gm_user_id
    ]
    return {
        "campaign": c,
        "gm_email": gm.email if gm else f"<user {c.gm_user_id}>",
        "members": members,
        "characters": characters,
        "maps": maps,
        "non_members": non_members,
        "all_users": db.query(User).order_by(User.id).all(),
    }


def add_member(db: Session, campaign_id: int, *, user_id: int) -> User:
    """Add a user to a campaign (idempotent — a no-op if already a member)."""
    if not db.query(Campaign).filter(Campaign.id == campaign_id).first():
        raise CampaignAdminError(f"No campaign with id {campaign_id}")
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise CampaignAdminError(f"No user with id {user_id}")
    existing = (
        db.query(CampaignMembership)
        .filter(
            CampaignMembership.campaign_id == campaign_id,
            CampaignMembership.user_id == user_id,
        ).first()
    )
    if not existing:
        db.add(CampaignMembership(campaign_id=campaign_id, user_id=user_id))
        db.commit()
    return u


def remove_member(db: Session, campaign_id: int, *, user_id: int) -> str:
    """Remove a user's membership. Returns the user's email (for the audit
    line). Idempotent — removing a non-member is a no-op."""
    u = db.query(User).filter(User.id == user_id).first()
    target = u.email if u else f"<user {user_id}>"
    db.query(CampaignMembership).filter(
        CampaignMembership.campaign_id == campaign_id,
        CampaignMembership.user_id == user_id,
    ).delete()
    db.commit()
    return target


def set_system(db: Session, campaign_id: int, *, game_system: str) -> str:
    """Set the campaign's game system (validated/normalized via get_system).
    Returns the resolved system key."""
    from ..game_systems import get_system
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise CampaignAdminError(f"No campaign with id {campaign_id}")
    c.game_system = get_system(game_system).key
    db.commit()
    return c.game_system


def create_character(db: Session, campaign_id: int, *, name: str, owner_user_id=None) -> Character:
    """Create a character in the campaign, forced to the campaign's locked
    system template (mirrors the in-app admin create)."""
    from ..game_systems import get_system
    from ..sheet_templates import get_template
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise CampaignAdminError(f"No campaign with id {campaign_id}")
    sys = get_system(c.game_system)
    char = Character(
        campaign_id=campaign_id,
        name=(name or "").strip()[:120] or "New character",
        template=sys.sheet_template,
        sheet=get_template(sys.sheet_template),
        owner_user_id=owner_user_id or None,
    )
    db.add(char)
    db.commit()
    db.refresh(char)
    return char


def assign_character(db: Session, campaign_id: int, char_id: int, *, owner_user_id=None) -> Character:
    """Set (or clear) a character's owner. Validates the character belongs to
    the campaign."""
    char = db.query(Character).filter(Character.id == char_id).first()
    if not char or char.campaign_id != campaign_id:
        raise CampaignAdminError(f"No character {char_id} in campaign {campaign_id}")
    char.owner_user_id = owner_user_id or None
    db.commit()
    return char


def delete_character(db: Session, campaign_id: int, char_id: int) -> str:
    """Delete a character. Returns its name (captured before delete)."""
    char = db.query(Character).filter(Character.id == char_id).first()
    if not char or char.campaign_id != campaign_id:
        raise CampaignAdminError(f"No character {char_id} in campaign {campaign_id}")
    name = char.name
    db.delete(char)
    db.commit()
    return name


def delete_campaign(db: Session, campaign_id: int) -> str:
    """Delete a campaign. Clears the self-referential ``active_map_id``
    first (so the maps cascade doesn't trip the FK), captures the name
    BEFORE the delete for the audit line, then deletes. Returns the name."""
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise CampaignAdminError(f"No campaign with id {campaign_id}")
    target_name = c.name
    c.active_map_id = None
    db.commit()
    db.delete(c)
    db.commit()
    return target_name
