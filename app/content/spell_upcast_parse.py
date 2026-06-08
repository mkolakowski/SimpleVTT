"""v2.125.0 — pure helper to derive a spell's per-slot up-cast dice from
its SRD-style ``higher_level`` prose.

Leaf module — no FastAPI / SQLAlchemy / hub dependencies — so both the
route layer (`app/routes/tabletop_routes.py`) and the in-process unit
tests import from here (mirrors `app/content/monster_action_parse.py`
and `app/content/effective_speed.py`).

Why this exists: the up-cast dice resolver (`_scale_dice_for_upcast`,
v2.110.0) scales a spell's damage/healing when a structured
``damage_per_slot`` / ``healing_per_slot`` field is present, but only a
few dozen of the ~319 SRD spells carry it (the rest were hand-backfilled
in v2.123.0/v2.124.0). Every spell *does* carry the rule in free-text
``higher_level``; this parser extracts the per-slot dice from that prose
so the long tail scales without a manual edit per spell. Manual JSON
fields always win — the resolver only consults the parser when the
structured field is absent.

**Deliberately conservative.** It returns a value ONLY for the
unambiguous "+Nd M for each slot level above" shape (per-1-slot) and
the "+Nd M for every two slot levels above" shape (per-2-slot;
v2.129.0 — Flame Blade, Spiritual Weapon). It returns ``{}`` (no
scaling) for:
  - Cantrip character-level scaling ("when you reach 5th level") — no
    slot to up-cast; handled by ``damage_scaling`` elsewhere.
  - Instance scaling ("one more dart/beam/target") — no dice term.
  - Flat bonuses ("increases by 10") — no dice term.
A false negative just leaves a spell un-scaled (the v1 status quo); a
false positive would mis-scale a cast, so the gates err toward silence.

The per-2 case returns ``upcast_step: 2`` alongside the dice; the
resolver divides ``(slot - base_level)`` by the step before scaling,
so Flame Blade at L4 grows by one extra die and at L6 by two extra
dice (RAW: "+1d6 for every two slot levels above 2nd").
"""
from __future__ import annotations

import re

# A dice term like "1d6" or "2d8". Captured so the caller gets "Nd M".
_DICE = r"(\d+d\d+)"

# The canonical slot-based up-cast clause:
#   "... increases by 1d6 for each slot level above 3rd"
#   "... the damage increases by 2d6 for each slot level above 7th"
# Require BOTH a dice term AND the "for each ... slot level above" tail so
# cantrip ("when you reach 5th level") and flat/instance clauses don't match.
_PER_SLOT = re.compile(
    _DICE + r"\s+for\s+each\s+(?:spell\s+)?slot\s+level\s+above",
    re.IGNORECASE,
)

# v2.129.0 — per-two-level slot scaling (Flame Blade / Spiritual Weapon):
#   "... the damage increases by 1d6 for every two slot levels above 2nd"
#   "... +1d8 for every two slot levels above the 2nd"
# Captured separately from `_PER_SLOT` so the resolver can apply a step=2
# divisor; otherwise the math undercounts the step.
_PER_TWO_SLOT = re.compile(
    _DICE + r"\s+for\s+every\s+two\s+(?:spell\s+)?slot\s+levels?\s+above",
    re.IGNORECASE,
)


def _classify_heal_or_damage(text: str, dice_start: int) -> bool:
    """True if the up-cast clause governs healing, False for damage.
    Looks at the prose leading up to the dice term — "the healing
    increases by 1d8 …" / "regains 2d8 hit points …"."""
    lead = text[:dice_start].lower()
    return ("healing" in lead) or ("hit points" in lead) or ("regains" in lead)


def parse_upcast_dice(higher_level: str | None) -> dict:
    """Return ``{"damage_per_slot": "Nd M"}`` /
    ``{"healing_per_slot": "Nd M"}`` (per-1-slot) or the same pair plus
    ``"upcast_step": 2`` (per-2-slot, v2.129.0), parsed from a spell's
    ``higher_level`` text. Returns ``{}`` when nothing scales
    unambiguously.

    Healing vs damage is decided by whether the word "healing" (or
    "hit points") governs the clause; otherwise it's treated as damage.
    """
    text = (higher_level or "").strip()
    if not text:
        return {}
    # v2.129.0 — try per-two-slot first so the broader per-1 pattern
    # doesn't accidentally swallow a "for every two slot levels" clause.
    m2 = _PER_TWO_SLOT.search(text)
    if m2:
        dice = m2.group(1)
        is_heal = _classify_heal_or_damage(text, m2.start())
        key = "healing_per_slot" if is_heal else "damage_per_slot"
        return {key: dice, "upcast_step": 2}
    m = _PER_SLOT.search(text)
    if not m:
        return {}
    dice = m.group(1)
    is_heal = _classify_heal_or_damage(text, m.start())
    return {"healing_per_slot" if is_heal else "damage_per_slot": dice}


def upcast_target_count(
    slot_level: int,
    base_level: int,
    *,
    base_targets: int = 1,
    per_slot: int = 1,
) -> int:
    """v2.127.0 — RAW max target count for a "+N targets per slot above
    base" up-cast (Hold Person, Hold Monster, Bless, …). Was copy-pasted
    as `max(1, slot_level - K)` across the dedicated cast endpoints; this
    is the single tested expression.

    ``base_targets`` creatures at ``base_level``, +``per_slot`` per slot
    level above it. Clamps below ``base_targets`` (so a defensively-low
    slot_level never returns 0). Examples:
      - Hold Person (base L2, 1 +1/slot): L2→1, L3→2, L4→3.
      - Hold Monster (base L5, 1 +1/slot): L5→1, L6→2, …, L9→5.
    """
    extra = max(0, int(slot_level) - int(base_level)) * int(per_slot)
    return max(int(base_targets), int(base_targets) + extra)


def upcast_pool_dice(
    slot_level: int,
    base_level: int,
    *,
    base_dice: int,
    per_slot_dice: int,
) -> int:
    """v2.128.0 — RAW dice COUNT for an HP-pool up-cast: ``base_dice``
    dice at ``base_level``, +``per_slot_dice`` per slot level above it.
    The caller appends the die size (Sleep is d8). Was inlined in the
    Sleep cast endpoint as ``5 + max(0, slot_level - 1) * 2``. Examples:
      - Sleep (base L1, 5d8 +2d8/slot): L1→5, L2→7, L3→9.
    Clamps below ``base_dice`` so a low slot_level never under-rolls.
    """
    extra = max(0, int(slot_level) - int(base_level)) * int(per_slot_dice)
    return max(int(base_dice), int(base_dice) + extra)
