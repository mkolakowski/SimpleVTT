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
unambiguous "+Nd M for each slot level above" shape (per-1-slot),
the "+Nd M for every two slot levels above" shape (per-2-slot;
v2.129.0 — Flame Blade, Spiritual Weapon), and the "+N for each
slot level above" flat-number shape (v2.130.0 — Aid, Heal,
False Life classifier). It returns ``{}`` (no scaling) for:
  - Cantrip character-level scaling ("when you reach 5th level") — no
    slot to up-cast; handled by ``damage_scaling`` elsewhere.
  - Instance scaling ("one more dart/beam/target") — no dice term.
A false negative just leaves a spell un-scaled (the v1 status quo); a
false positive would mis-scale a cast, so the gates err toward silence.

The per-2 case returns ``upcast_step: 2`` alongside the dice; the
resolver divides ``(slot - base_level)`` by the step before scaling,
so Flame Blade at L4 grows by one extra die and at L6 by two extra
dice (RAW: "+1d6 for every two slot levels above 2nd").

The flat case emits ``flat_damage_per_slot`` / ``flat_healing_per_slot``
(integer) alongside the dice fields; the resolver routes this through
``_scale_flat_for_upcast`` instead of ``_scale_dice_for_upcast`` so a
"+5 per slot" clause grows a flat base ("70" → "80") or a dice base
with a +N suffix ("1d4+4" → "1d4+9") without inventing dice.
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

# v2.130.0 — flat-number per-slot scaling (Aid, False Life, Heal):
#   "the amount of healing increases by 10 for each slot level above 6th"
#   "a target's hit points increase by an additional 5 for each slot level above 2nd"
#   "you gain 5 additional temporary hit points for each slot level above 1st"
# `\b\d+\b` excludes digits inside a dice term ("6" in "1d6" has no word boundary
# before it because "d" is also a word char). Optional intervening prose
# ("additional", "additional temporary hit points") between the number and the
# "for each slot level above" tail. The dice-pattern regexes are tried FIRST in
# `parse_upcast_dice` so a "+1d6 for each" clause never reaches this branch.
_PER_SLOT_FLAT = re.compile(
    r"\b(\d+)\b"
    r"(?:\s+additional)?"
    r"(?:\s+(?:temporary\s+)?hit\s+points?)?"
    r"\s+for\s+each\s+(?:spell\s+)?slot\s+level\s+above",
    re.IGNORECASE,
)


def _classify_heal_or_damage(text: str, dice_start: int = 0) -> bool:
    """True if the up-cast clause governs healing, False for damage.
    Searches the full ``text`` for any of the heal keywords — "healing"
    (Cure Wounds, Heal), "hit points" (Aid, False Life), or "regains"
    (Mass Healing Word) — so the False Life shape ("you gain 5 …
    temporary hit points") classifies correctly even though "hit
    points" appears AFTER the dice term. False positives are rare
    enough in the SRD corpus that this is safe; if a damage clause
    ever mentions "healing" it'd need a structured override anyway.
    ``dice_start`` is accepted for back-compat with the v2.125.0
    signature but ignored."""
    t = text.lower()
    return ("healing" in t) or ("hit points" in t) or ("regains" in t)


def parse_upcast_dice(higher_level: str | None) -> dict:
    """Return ``{"damage_per_slot": "Nd M"}`` /
    ``{"healing_per_slot": "Nd M"}`` (per-1-slot dice), the same pair
    plus ``"upcast_step": 2`` (per-2-slot dice, v2.129.0), or
    ``{"flat_damage_per_slot": N}`` / ``{"flat_healing_per_slot": N}``
    (per-1-slot flat number, v2.130.0) parsed from a spell's
    ``higher_level`` text. Returns ``{}`` when nothing scales
    unambiguously.

    Healing vs damage is decided by whether ``healing`` / ``hit points``
    / ``regains`` appears anywhere in the clause; otherwise damage.
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
    if m:
        dice = m.group(1)
        is_heal = _classify_heal_or_damage(text, m.start())
        return {"healing_per_slot" if is_heal else "damage_per_slot": dice}
    # v2.130.0 — flat-number per-slot scaling. Only reached when neither
    # dice regex matched, so a clause like "increases by 1d6 for each
    # slot level above" never hits this branch.
    mf = _PER_SLOT_FLAT.search(text)
    if mf:
        flat = int(mf.group(1))
        is_heal = _classify_heal_or_damage(text, mf.start())
        key = "flat_healing_per_slot" if is_heal else "flat_damage_per_slot"
        return {key: flat}
    return {}


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


def scale_flat_for_upcast(base_expr, per_slot_flat, extra_levels):
    """v2.130.0 — add ``extra_levels × per_slot_flat`` flat HP / damage
    to ``base_expr``. Used by Heal-style up-cast (RAW: "+10 healing per
    slot above 6th"), where the per-slot bonus is a constant integer
    rather than dice.

    Three base shapes:
      - Pure flat ("70"):           '70'    + 10 → '80'
      - Dice with +N suffix:        '1d4+4' + 5  → '1d4+9'  (merge into +N)
      - Pure dice ("1d4"):          '1d4'   + 5  → '1d4+5'  (append +N)

    Returns ``base_expr`` unchanged on missing inputs OR an unparseable
    base (so a future spell with a complex base like '1d8+1d6' is a
    no-op rather than a mis-scale)."""
    base = (base_expr or "").strip()
    if not base or not per_slot_flat or (extra_levels or 0) <= 0:
        return base
    try:
        add_n = int(per_slot_flat) * int(extra_levels)
    except (TypeError, ValueError):
        return base
    if add_n == 0:
        return base
    m_flat = re.match(r"^(\d+)$", base)
    if m_flat:
        return str(int(m_flat.group(1)) + add_n)
    m_dice_plus = re.match(r"^(\d+d\d+)\s*\+\s*(\d+)\s*$", base)
    if m_dice_plus:
        return f"{m_dice_plus.group(1)}+{int(m_dice_plus.group(2)) + add_n}"
    m_dice = re.match(r"^\d+d\d+$", base)
    if m_dice:
        return f"{base}+{add_n}"
    return base


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
