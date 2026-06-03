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


def effective_speed_walk(combatant: dict | None) -> int:
    """Return ``combatant.speed_walk`` minus the sum of speed-
    reduction effects from active buffs, clamped to a minimum of 0.
    Pure derivation; does not mutate the combatant.
    """
    if not combatant:
        return 30
    try:
        base = int(combatant.get("speed_walk") or 30)
    except (TypeError, ValueError):
        base = 30
    reduction = effective_speed_reduction_ft(combatant)
    return max(0, base - reduction)
