"""v2.99.98 — pure helpers for computing a combatant's effective
walking speed after speed-reduction buffs.

Leaf module — no FastAPI / SQLAlchemy / hub dependencies. Both
the route layer (`app/routes/tabletop_routes.py`) and the
in-process unit tests (`tests/harness/test_effective_speed_walk.py`)
import from here.

The pair mirrors the JS-side `_effectiveSpeedWalk` /
`_effectiveSpeedReductionFt` in `app/templates/tabletop.html`. Both
sides walk `combatant.buffs[]` for `effects.speed_reduction_ft`
and subtract the sum from `combatant.speed_walk` (clamped to ≥ 0).
The v2.99.92 Lance of Lethargy buff installs that field; future
sources (Slow spell, web, grease, monster grappler features) can
install the same field and the helpers will pick them up.
"""
from __future__ import annotations


def effective_speed_reduction_ft(combatant: dict | None) -> int:
    """Sum the active speed-reduction effects on a combatant's buff
    list. Returns 0 when:
      - combatant is None / has no buffs
      - no buff carries ``effects.speed_reduction_ft``
      - the effects field is non-dict (legacy descriptive shape)
    """
    if not combatant:
        return 0
    buffs = combatant.get("buffs") or []
    if not isinstance(buffs, list):
        return 0
    total = 0
    for b in buffs:
        if not isinstance(b, dict):
            continue
        effects = b.get("effects")
        if not isinstance(effects, dict):
            continue
        try:
            total += int(effects.get("speed_reduction_ft") or 0)
        except (TypeError, ValueError):
            continue
    return max(0, total)


def effective_speed_bonus_ft(combatant: dict | None) -> int:
    """v2.99.431 — Phase 6.1: sum the active speed-BONUS effects on a
    combatant's buff list (``effects.speed_bonus_ft``). The additive
    complement to ``effective_speed_reduction_ft`` — Longstrider (+10),
    Eagle Totem / Step of the Wind dash bonuses, etc. install this key.
    Returns 0 on the same empty/non-dict guards.
    """
    if not combatant:
        return 0
    buffs = combatant.get("buffs") or []
    if not isinstance(buffs, list):
        return 0
    total = 0
    for b in buffs:
        if not isinstance(b, dict):
            continue
        effects = b.get("effects")
        if not isinstance(effects, dict):
            continue
        try:
            total += int(effects.get("speed_bonus_ft") or 0)
        except (TypeError, ValueError):
            continue
    return max(0, total)


def effective_speed_multiplier(combatant: dict | None) -> int:
    """v2.99.431 — Phase 6.1: the largest ``effects.speed_multiplier`` on
    a combatant's buffs (default 1). Haste doubles your speed
    (``speed_multiplier: 2``). RAW these don't stack — take the max.
    """
    if not combatant:
        return 1
    buffs = combatant.get("buffs") or []
    if not isinstance(buffs, list):
        return 1
    best = 1
    for b in buffs:
        if not isinstance(b, dict):
            continue
        effects = b.get("effects")
        if not isinstance(effects, dict):
            continue
        try:
            m = int(effects.get("speed_multiplier") or 1)
        except (TypeError, ValueError):
            m = 1
        if m > best:
            best = m
    return best


def effective_speed_walk(combatant: dict | None) -> int:
    """Return a combatant's effective walking speed: ``(speed_walk +
    Σ speed_bonus_ft) × speed_multiplier − Σ speed_reduction_ft``,
    clamped to a minimum of 0. Pure derivation; does not mutate the
    combatant.

    v2.99.431 — Phase 6.1 added the bonus + multiplier terms (Longstrider
    / Haste / Eagle Totem); pre-v2.99.431 this was ``base − reduction``
    only. Haste's ×2 applies to the buffed base before reductions
    (RAW "your speed is doubled").
    """
    if not combatant:
        return 30
    try:
        base = int(combatant.get("speed_walk") or 30)
    except (TypeError, ValueError):
        base = 30
    bonus = effective_speed_bonus_ft(combatant)
    mult = effective_speed_multiplier(combatant)
    reduction = effective_speed_reduction_ft(combatant)
    return max(0, (base + bonus) * mult - reduction)
