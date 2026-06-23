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
        {"email": u.email, "display_name": u.display_name, "is_gm": m.is_gm}
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
    return {
        "campaign": c,
        "gm_email": gm.email if gm else f"<user {c.gm_user_id}>",
        "members": members,
        "characters": characters,
        "maps": maps,
    }


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
