"""FK-safe deletion of a campaign's child rows.

Phase 2 of the backup/export-import arc
(``docs/plans/backup-export-overhaul.md``). Extracted verbatim from the
per-campaign block of ``demo_seed.wipe()`` so the importer's restore path
(Phase 7) can reuse the exact ordering the demo reseed has relied on for
many releases, instead of re-deriving a fragile delete sequence.

The order matters: tokens reference maps; ``campaigns.active_map_id``
points at a map via a ``use_alter`` FK with no ``ondelete`` clause (it
breaks the campaigns↔maps cycle), so it must be nulled before the maps
are dropped. The function deletes **child rows only** — never the
``campaigns`` row itself, and it neither flushes nor commits (the caller
owns the transaction boundary: ``demo_seed.wipe`` deletes the campaign +
users after this and commits once; the importer keeps the campaign row).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Campaign,
    CampaignMembership,
    Character,
    DiceRoll,
    Encounter,
    Map,
    Token,
    TokenTemplate,
)


def wipe_campaign_children(
    db: Session,
    campaign_ids: list[int],
    *,
    delete_memberships: bool = True,
) -> dict[str, int]:
    """Delete the per-campaign child rows for ``campaign_ids`` in FK-safe
    order. Returns per-table delete counts.

    ``delete_memberships`` defaults to True to match ``demo_seed.wipe``'s
    behavior (the demo reseed drops the campaign wholesale, memberships
    included). The importer's restore path passes ``False`` — a restore
    replaces *content* but keeps the people in the campaign.

    Does not delete the ``campaigns`` row, flush, or commit.
    """
    counts: dict[str, int] = {}
    if not campaign_ids:
        return counts

    # Tokens (FK to maps in the campaign).
    map_id_subq = select(Map.id).where(Map.campaign_id.in_(campaign_ids))
    counts["tokens"] = (
        db.query(Token)
        .filter(Token.map_id.in_(map_id_subq))
        .delete(synchronize_session=False)
    )
    # Encounters.
    counts["encounters"] = (
        db.query(Encounter)
        .filter(Encounter.campaign_id.in_(campaign_ids))
        .delete(synchronize_session=False)
    )
    # DiceRolls.
    counts["dice_rolls"] = (
        db.query(DiceRoll)
        .filter(DiceRoll.campaign_id.in_(campaign_ids))
        .delete(synchronize_session=False)
    )
    # TokenTemplates.
    counts["token_templates"] = (
        db.query(TokenTemplate)
        .filter(TokenTemplate.campaign_id.in_(campaign_ids))
        .delete(synchronize_session=False)
    )
    # Characters.
    counts["characters"] = (
        db.query(Character)
        .filter(Character.campaign_id.in_(campaign_ids))
        .delete(synchronize_session=False)
    )
    # Null out campaigns.active_map_id before deleting maps — the
    # ``fk_campaign_active_map`` FK has no ondelete clause (declared with
    # ``use_alter`` to break the campaigns↔maps cycle), so a DELETE on
    # maps while a campaign still points at one raises ForeignKeyViolation.
    db.query(Campaign).filter(
        Campaign.id.in_(campaign_ids)
    ).update({Campaign.active_map_id: None}, synchronize_session=False)
    # Maps.
    counts["maps"] = (
        db.query(Map)
        .filter(Map.campaign_id.in_(campaign_ids))
        .delete(synchronize_session=False)
    )
    # Memberships.
    if delete_memberships:
        counts["memberships"] = (
            db.query(CampaignMembership)
            .filter(CampaignMembership.campaign_id.in_(campaign_ids))
            .delete(synchronize_session=False)
        )

    return counts
