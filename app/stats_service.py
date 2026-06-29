"""Per-campaign statistics aggregation (see docs/plans/campaign-stats.md).

Turns the ``campaign_stat_events`` event log into the numbers the stats
page shows — per-character totals, per-session breakdowns, and top-N
spells. Kept out of the (very large) ``tabletop_routes.py`` so it's
unit-testable on its own.

The write side (capture hooks) lives in ``tabletop_routes.py``
(``_log_stat_event`` + Hooks A–D); this module is read-only.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import CampaignStatEvent as _Ev


def _coalesce_sum(event_type: str):
    return func.coalesce(
        func.sum(_Ev.amount).filter(_Ev.event_type == event_type), 0
    )


def character_totals(db: Session, campaign_id: int, char_id: int) -> dict:
    """Lifetime totals for one character in one campaign."""
    row = db.query(
        _coalesce_sum("damage_dealt").label("damage_dealt"),
        _coalesce_sum("damage_taken").label("damage_taken"),
        _coalesce_sum("heal_done").label("heal_done"),
        _coalesce_sum("heal_received").label("heal_received"),
        func.count().filter(_Ev.event_type == "attack").label("attacks"),
        func.count().filter(
            (_Ev.event_type == "attack") & (_Ev.is_hit.is_(True))
        ).label("hits"),
        func.count().filter(
            (_Ev.event_type == "attack") & (_Ev.is_crit.is_(True))
        ).label("crits"),
        func.count().filter(_Ev.event_type == "ko").label("kos"),
        func.count().filter(
            _Ev.event_type == "spell_cast"
        ).label("spells_cast"),
        func.coalesce(
            func.max(_Ev.amount).filter(_Ev.event_type == "damage_dealt"), 0
        ).label("biggest_hit"),
    ).filter(
        _Ev.campaign_id == campaign_id,
        _Ev.actor_char_id == char_id,
    ).one()

    attacks = int(row.attacks or 0)
    hits = int(row.hits or 0)
    return {
        "damage_dealt": int(row.damage_dealt or 0),
        "damage_taken": int(row.damage_taken or 0),
        "heal_done": int(row.heal_done or 0),
        "heal_received": int(row.heal_received or 0),
        "attacks": attacks,
        "hits": hits,
        "crits": int(row.crits or 0),
        "kos": int(row.kos or 0),
        "spells_cast": int(row.spells_cast or 0),
        "biggest_hit": int(row.biggest_hit or 0),
        "hit_rate": round(hits / attacks, 3) if attacks else None,
    }


def character_top_spells(
    db: Session, campaign_id: int, char_id: int, limit: int = 5,
) -> list[dict]:
    """The character's most-cast spells (by ``spell_slug``)."""
    rows = (
        db.query(
            _Ev.spell_slug,
            func.max(_Ev.spell_name).label("name"),
            func.count().label("count"),
        )
        .filter(
            _Ev.campaign_id == campaign_id,
            _Ev.actor_char_id == char_id,
            _Ev.event_type == "spell_cast",
            _Ev.spell_slug.isnot(None),
        )
        .group_by(_Ev.spell_slug)
        .order_by(func.count().desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "spell_slug": r.spell_slug,
            "spell_name": r.name or r.spell_slug,
            "count": int(r.count),
        }
        for r in rows
    ]


def character_by_session(
    db: Session, campaign_id: int, char_id: int,
) -> list[dict]:
    """Per-session breakdown (damage dealt/taken + healing) for one
    character, ordered by first event in the session."""
    rows = (
        db.query(
            _Ev.session_key,
            _coalesce_sum("damage_dealt").label("dd"),
            _coalesce_sum("damage_taken").label("dt"),
            _coalesce_sum("heal_done").label("hd"),
            func.min(_Ev.created_at).label("first"),
        )
        .filter(
            _Ev.campaign_id == campaign_id,
            _Ev.actor_char_id == char_id,
        )
        .group_by(_Ev.session_key)
        .order_by(func.min(_Ev.created_at))
        .all()
    )
    return [
        {
            "session_key": r.session_key,
            "damage_dealt": int(r.dd or 0),
            "damage_taken": int(r.dt or 0),
            "heal_done": int(r.hd or 0),
        }
        for r in rows
    ]


def character_block(
    db: Session, campaign_id: int, char_id: int, char_name: str,
) -> dict:
    """Assemble the full per-character stats block the API returns."""
    return {
        "id": char_id,
        "name": char_name,
        "totals": character_totals(db, campaign_id, char_id),
        "top_spells": character_top_spells(db, campaign_id, char_id),
        "by_session": character_by_session(db, campaign_id, char_id),
    }


def campaign_activity_report(db: Session, campaign_id: int) -> dict:
    """v2.730.0 — campaign-wide ACTIVITY summary for the GM Reporting page
    (docs: the "Reporting Page" GM-Tools item). Distinct from the per-character
    combat stats page — this answers "how much has happened, across how many
    sessions, and who's been most active." Derived entirely from the existing
    `campaign_stat_events` log (no new capture).

    Returns ``{session_count, total_events, events_by_type, per_session,
    top_actors}``.
    """
    base = db.query(_Ev).filter(_Ev.campaign_id == campaign_id)
    total_events = base.count()
    session_count = (
        db.query(func.count(func.distinct(_Ev.session_key)))
        .filter(_Ev.campaign_id == campaign_id)
        .scalar()
    ) or 0

    # Event counts by type (the engagement mix).
    type_rows = (
        db.query(_Ev.event_type, func.count().label("n"))
        .filter(_Ev.campaign_id == campaign_id)
        .group_by(_Ev.event_type)
        .all()
    )
    events_by_type = {r.event_type: int(r.n) for r in type_rows}

    # Per-session activity timeline (event volume + headline damage/heal).
    sess_rows = (
        db.query(
            _Ev.session_key,
            func.count().label("events"),
            _coalesce_sum("damage_dealt").label("dd"),
            _coalesce_sum("heal_done").label("hd"),
            func.min(_Ev.created_at).label("first"),
        )
        .filter(_Ev.campaign_id == campaign_id)
        .group_by(_Ev.session_key)
        .order_by(func.min(_Ev.created_at))
        .all()
    )
    per_session = [
        {
            "session_key": r.session_key,
            "events": int(r.events or 0),
            "damage_dealt": int(r.dd or 0),
            "heal_done": int(r.hd or 0),
            "first": r.first.isoformat() if r.first else None,
        }
        for r in sess_rows
    ]

    # Most active actors (by recorded event count) — "active players over time".
    # v2.736.0 — also surface actor_char_id (max-per-name; a name maps to one
    # character) so the report can link PC actors to their sheet. NPC actors
    # have NULL char_id → name-only.
    actor_rows = (
        db.query(
            _Ev.actor_name,
            func.max(_Ev.actor_char_id).label("cid"),
            func.count().label("n"),
        )
        .filter(
            _Ev.campaign_id == campaign_id,
            _Ev.actor_name.isnot(None),
            _Ev.actor_name != "",
        )
        .group_by(_Ev.actor_name)
        .order_by(func.count().desc())
        .limit(15)
        .all()
    )
    top_actors = [
        {"name": r.actor_name, "char_id": r.cid, "events": int(r.n)}
        for r in actor_rows
    ]

    # v2.734.0 — token-movement summary (the "token move history" slice of the
    # Reporting Page). token_move events carry the distance in `amount`.
    move_row = (
        db.query(
            func.count().label("moves"),
            func.coalesce(func.sum(_Ev.amount), 0).label("dist"),
        )
        .filter(
            _Ev.campaign_id == campaign_id,
            _Ev.event_type == "token_move",
        )
        .first()
    )
    total_moves = int(move_row.moves or 0) if move_row else 0
    total_distance_ft = int(move_row.dist or 0) if move_row else 0

    return {
        "session_count": int(session_count),
        "total_events": int(total_events),
        "events_by_type": events_by_type,
        "per_session": per_session,
        "top_actors": top_actors,
        "total_moves": total_moves,
        "total_distance_ft": total_distance_ft,
    }


def session_detail(db: Session, campaign_id: int, session_key: str) -> dict:
    """v2.735.0 — drill-down detail for one session: its event mix, most-active
    actors, headline totals (damage/heal/moves/distance), and a recent-events
    list. Backs the per-session view linked from the activity report."""
    scope = (
        db.query(_Ev)
        .filter(_Ev.campaign_id == campaign_id, _Ev.session_key == session_key)
    )
    total_events = scope.count()

    type_rows = (
        db.query(_Ev.event_type, func.count().label("n"))
        .filter(_Ev.campaign_id == campaign_id, _Ev.session_key == session_key)
        .group_by(_Ev.event_type)
        .all()
    )
    events_by_type = {r.event_type: int(r.n) for r in type_rows}

    actor_rows = (
        db.query(
            _Ev.actor_name,
            func.max(_Ev.actor_char_id).label("cid"),
            func.count().label("n"),
        )
        .filter(
            _Ev.campaign_id == campaign_id, _Ev.session_key == session_key,
            _Ev.actor_name.isnot(None), _Ev.actor_name != "",
        )
        .group_by(_Ev.actor_name)
        .order_by(func.count().desc())
        .limit(15)
        .all()
    )
    top_actors = [
        {"name": r.actor_name, "char_id": r.cid, "events": int(r.n)}
        for r in actor_rows
    ]

    tot = (
        db.query(
            _coalesce_sum("damage_dealt").label("dd"),
            _coalesce_sum("heal_done").label("hd"),
            func.count().filter(_Ev.event_type == "token_move").label("moves"),
            func.coalesce(
                func.sum(_Ev.amount).filter(_Ev.event_type == "token_move"), 0
            ).label("dist"),
        )
        .filter(_Ev.campaign_id == campaign_id, _Ev.session_key == session_key)
        .first()
    )

    recent = (
        db.query(_Ev)
        .filter(_Ev.campaign_id == campaign_id, _Ev.session_key == session_key)
        .order_by(_Ev.created_at.desc())
        .limit(150)
        .all()
    )
    recent_events = [
        {
            "actor_name": e.actor_name or "—",
            "event_type": e.event_type,
            "amount": e.amount,
            "target_name": e.target_name or "",
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in recent
    ]

    return {
        "session_key": session_key,
        "total_events": int(total_events),
        "events_by_type": events_by_type,
        "top_actors": top_actors,
        "total_damage_dealt": int(tot.dd or 0) if tot else 0,
        "total_heal_done": int(tot.hd or 0) if tot else 0,
        "total_moves": int(tot.moves or 0) if tot else 0,
        "total_distance_ft": int(tot.dist or 0) if tot else 0,
        "recent_events": recent_events,
    }


def actor_char_ids(db: Session, campaign_id: int) -> list[int]:
    """Distinct non-null actor character ids that have any stat events in
    the campaign — the GM-view roster of who has recorded stats."""
    rows = (
        db.query(_Ev.actor_char_id)
        .filter(
            _Ev.campaign_id == campaign_id,
            _Ev.actor_char_id.isnot(None),
        )
        .distinct()
        .all()
    )
    return [int(r[0]) for r in rows if r[0] is not None]
