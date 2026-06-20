"""Database data-inventory for the admin center.

A read-only roll-up of how many rows of each kind SimpleVTT stores —
the database-side companion to the audit log + the privacy policy's
data inventory ("here's what we hold on you, by the numbers").

Imports of the app's DB layer + ORM models are **lazy** (inside the
function) so importing this module never triggers engine creation —
the engine in ``app/database.py`` is built at import time from config,
which isn't available when the other admin-center modules are
unit-tested on a host without a database. The endpoint calls
``read_inventory()`` at request time, inside the container where the
DB is reachable.
"""
from __future__ import annotations


def read_inventory() -> dict:
    """Return ``{available, counts, breakdown}`` row counts, or
    ``{available: False, reason}`` when the DB is unreachable."""
    try:
        from sqlalchemy import func

        from ..database import SessionLocal
        from ..models import (
            Campaign,
            CampaignMembership,
            Character,
            DiceRoll,
            Encounter,
            Map,
            Playlist,
            Token,
            User,
        )
    except Exception as e:  # noqa: BLE001 — DB layer not importable
        return {"available": False, "reason": f"DB layer unavailable: {e}", "counts": {}, "breakdown": {}}

    # (label, model) — ordered for display.
    tables = [
        ("Users", User),
        ("Campaigns", Campaign),
        ("Characters", Character),
        ("Campaign memberships", CampaignMembership),
        ("Dice rolls", DiceRoll),
        ("Maps", Map),
        ("Tokens", Token),
        ("Encounters", Encounter),
        ("Playlists", Playlist),
    ]

    counts: dict[str, int] = {}
    breakdown: dict[str, int] = {}
    try:
        with SessionLocal() as db:
            for label, model in tables:
                counts[label] = int(
                    db.query(func.count()).select_from(model).scalar() or 0
                )
            # Account-shape breakdown — mirrors the privacy ledger's
            # "who's an admin / how do they sign in" questions.
            breakdown["Admins"] = int(
                db.query(func.count()).select_from(User)
                .filter(User.is_admin.is_(True)).scalar() or 0
            )
            breakdown["Disabled accounts"] = int(
                db.query(func.count()).select_from(User)
                .filter(User.is_disabled.is_(True)).scalar() or 0
            )
            breakdown["Google SSO accounts"] = int(
                db.query(func.count()).select_from(User)
                .filter(User.google_sub.isnot(None)).scalar() or 0
            )
            breakdown["Password accounts"] = int(
                db.query(func.count()).select_from(User)
                .filter(User.password_hash.isnot(None)).scalar() or 0
            )
    except Exception as e:  # noqa: BLE001 — DB down / mid-migration
        return {"available": False, "reason": f"DB query failed: {e}", "counts": {}, "breakdown": {}}

    return {"available": True, "counts": counts, "breakdown": breakdown}
