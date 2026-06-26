"""v2.159.27 — carrying-capacity Phase 1 leaf module.

Pure helpers for computing a PC's carrying capacity (`STR × 15 lb`)
and current inventory weight. RAW PHB p.176. See
`docs/plans/carrying-capacity.md` for the design.

Leaf module — no FastAPI / SQLAlchemy / hub dependencies. The route
layer (`app/routes/tabletop_routes.py`) and the unit tests
(`tests/harness/test_carry_weight.py`) import from here.

Three sources for an inventory item's weight, in priority order:
  1. ``item.weight_lb`` (int/float) — set on PCs whose sheet authors
     populate the field explicitly.
  2. Parsed from ``item.weight`` (a string from the SRD JSON like
     ``"3 lb."`` or the known ``"3 lb. lb"`` typo). Used when the PC
     sheet doesn't carry a numeric override.
  3. Default 0 for items with no weight data.
"""
from __future__ import annotations

import re
from typing import Iterable


# ── Weight string parser ─────────────────────────────────────────────────────

_FRAC_NUM_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
_LEADING_NUMERIC_RE = re.compile(r"^\s*([0-9]+(?:[./][0-9]+)?)")


def parse_weight_lb(weight_str: "str | None") -> float:
    """Parse the inconsistent SRD-catalog weight strings into a float.

    Handles:
      - ``""``                  → 0.0 (missing weight metadata).
      - ``"3 lb."``             → 3.0
      - ``"3 lb. lb"``          → 3.0 (known SRD typo on some items).
      - ``"15 lb."``            → 15.0
      - ``"1/2 lb."``           → 0.5
      - ``"2.5 lb."``           → 2.5
      - ``None`` / non-string   → 0.0 (defensive).
      - ``"unparsable junk"``   → 0.0 (no leading numeric).

    Strategy: pull the leading numeric token (integer, decimal, or
    `n/m` fraction) and ignore the trailing unit text. The SRD always
    expresses item weight in pounds — there's no need to recognize
    units. RAW item weights are never negative.
    """
    if not isinstance(weight_str, str):
        return 0.0
    stripped = weight_str.strip()
    if not stripped:
        return 0.0
    # Fraction shape ``"1/2 lb."`` — the leading-numeric regex below
    # would only catch "1" and miss the denominator. Special-case it.
    head = stripped.split(" ", 1)[0]
    frac_match = _FRAC_NUM_RE.match(head)
    if frac_match:
        try:
            num = float(frac_match.group(1))
            den = float(frac_match.group(2))
            if den == 0:
                return 0.0
            return max(0.0, num / den)
        except (TypeError, ValueError):
            return 0.0
    # Integer or decimal — pull the leading numeric run.
    m = _LEADING_NUMERIC_RE.match(stripped)
    if not m:
        return 0.0
    try:
        return max(0.0, float(m.group(1)))
    except (TypeError, ValueError):
        return 0.0


def item_weight_lb(
    item: dict,
    fallback_catalog_weight: "str | None" = None,
) -> float:
    """Resolve a single inventory item's weight via the 3-tier
    priority order:
      1. ``item.weight_lb`` (numeric) — explicit override.
      2. Parsed from ``item.weight`` (string) on the item itself.
      3. ``fallback_catalog_weight`` parsed (string from the catalog).
      4. 0.0 fallback.
    """
    if not isinstance(item, dict):
        return 0.0
    direct = item.get("weight_lb")
    if isinstance(direct, (int, float)):
        return max(0.0, float(direct))
    on_item = item.get("weight")
    if isinstance(on_item, str):
        parsed = parse_weight_lb(on_item)
        if parsed > 0:
            return parsed
    if isinstance(fallback_catalog_weight, str):
        return parse_weight_lb(fallback_catalog_weight)
    return 0.0


# ── Carrying capacity ────────────────────────────────────────────────────────


def _str_score_from_sheet(sheet: dict) -> int:
    """Pull the PC's Strength score off the sheet. Falls back to 10
    (default human) on missing / malformed fields. Tries the most
    common shapes the codebase uses for ability scores:
      - ``sheet.abilities.STR`` (the dnd5e demo seed's shape).
      - ``sheet.abilities.strength`` / ``sheet.abilities.str``.
      - Nested ``{"score": 14, "mod": 2}`` value.
      - Flat ``sheet.str`` / ``sheet.strength`` (legacy)."""
    if not isinstance(sheet, dict):
        return 10
    abilities = sheet.get("abilities")
    if isinstance(abilities, dict):
        for k in ("STR", "strength", "str", "Str"):
            v = abilities.get(k)
            if isinstance(v, (int, float)):
                return max(1, min(30, int(v)))
            if isinstance(v, dict):
                # Some sheets nest the score: {"score": 14, "mod": 2}.
                inner = v.get("score")
                if isinstance(inner, (int, float)):
                    return max(1, min(30, int(inner)))
    flat = sheet.get("str") or sheet.get("strength") or sheet.get("STR")
    if isinstance(flat, (int, float)):
        return max(1, min(30, int(flat)))
    return 10


def sheet_carry_capacity_lb(
    sheet: dict,
    effective_str: "int | None" = None,
) -> int:
    """RAW PHB p.176: carrying capacity = ``STR × 15 lb``. Returns
    an integer (RAW; weight thresholds are always whole numbers).

    v2.212.0 — ability-score override (Belt of Giant Strength etc.,
    docs/plans/str-override.md). The route layer resolves the EFFECTIVE
    STR (folding equipped-item overrides over the base) and passes it
    in; when ``effective_str`` is None this falls back to the stored
    score so the leaf module stays pure (no item-passive knowledge)."""
    str_score = effective_str if isinstance(effective_str, int) else _str_score_from_sheet(sheet)
    return max(1, str_score) * 15


def sheet_inventory_weight_lb(
    sheet: dict,
    catalog_weight_by_slug: "dict[str, str] | None" = None,
) -> float:
    """Sum ``item_weight_lb × qty`` across the PC's ``inventory[]``.

    ``catalog_weight_by_slug`` is an optional lookup from item slug to
    the catalog JSON's ``weight`` string. Used as the 3rd-tier fallback
    when the inventory item doesn't carry an override. When None, the
    helper just reads from the inventory item.

    v2.159.27 — Bag of Holding (filed for Phase 3): when an item
    carries ``_in_bag_of_holding: True``, its weight is excluded from
    the sum. The Bag itself stays in the inventory (15 lb).
    """
    if not isinstance(sheet, dict):
        return 0.0
    inv = sheet.get("inventory") or []
    if not isinstance(inv, list):
        return 0.0
    total = 0.0
    for item in inv:
        if not isinstance(item, dict):
            continue
        # v2.159.27 — Phase 3 Bag of Holding hook (the catalog row is
        # filed for next commit; the read site lands here now so the
        # follow-up doesn't need to re-touch this helper).
        if item.get("_in_bag_of_holding"):
            continue
        try:
            qty = int(item.get("qty") or 1)
        except (TypeError, ValueError):
            qty = 1
        if qty <= 0:
            continue
        catalog_w = None
        if catalog_weight_by_slug:
            slug = str(item.get("_slug") or "").strip().lower()
            if slug:
                catalog_w = catalog_weight_by_slug.get(slug)
        weight = item_weight_lb(item, catalog_w)
        total += weight * qty
    return total


# RAW DMG p.153: a Bag of Holding holds up to 500 lb. Overloading it
# ruptures the bag (contents scattered to the Astral Plane). v2.656.0
# tracks the in-bag weight so the carry meter can flag the rupture —
# previously the 500-lb cap was descriptive-only (unenforced).
BAG_OF_HOLDING_CAPACITY_LB = 500.0


def sheet_bag_of_holding_weight_lb(
    sheet: dict,
    catalog_weight_by_slug: "dict[str, str] | None" = None,
) -> float:
    """Sum ``item_weight_lb × qty`` across inventory items flagged
    ``_in_bag_of_holding: True`` — i.e. the weight that
    ``sheet_inventory_weight_lb`` excludes from the wielder's burden.
    Used to surface the Bag of Holding's RAW 500-lb internal capacity."""
    if not isinstance(sheet, dict):
        return 0.0
    inv = sheet.get("inventory") or []
    if not isinstance(inv, list):
        return 0.0
    total = 0.0
    for item in inv:
        if not isinstance(item, dict) or not item.get("_in_bag_of_holding"):
            continue
        try:
            qty = int(item.get("qty") or 1)
        except (TypeError, ValueError):
            qty = 1
        if qty <= 0:
            continue
        catalog_w = None
        if catalog_weight_by_slug:
            slug = str(item.get("_slug") or "").strip().lower()
            if slug:
                catalog_w = catalog_weight_by_slug.get(slug)
        total += item_weight_lb(item, catalog_w) * qty
    return total


def sheet_is_over_capacity(
    sheet: dict,
    catalog_weight_by_slug: "dict[str, str] | None" = None,
    effective_str: "int | None" = None,
) -> bool:
    """True when current inventory weight exceeds carry capacity."""
    return (
        sheet_inventory_weight_lb(sheet, catalog_weight_by_slug)
        > sheet_carry_capacity_lb(sheet, effective_str)
    )


# ── Encumbrance variant (PHB p.176) ──────────────────────────────────────────

# RAW PHB p.176 "Variant: Encumbrance" — the two penalty thresholds are
# multiples of the STR score:
#   - weight > STR × 5   → encumbered          (speed −10 ft)
#   - weight > STR × 10  → heavily encumbered  (speed −20 ft + disadvantage
#                                               on STR/DEX/CON checks, attacks,
#                                               and saves)
# (STR × 15 is the normal maximum carrying capacity — see
# ``sheet_carry_capacity_lb`` — beyond which you can't effectively move.)
#
# NOTE: docs/plans/carrying-capacity.md (Phase 4 + the RAW summary) mis-stated
# these as STR × 10 / STR × 15. The correct RAW variant thresholds are
# STR × 5 / STR × 10, implemented here; the plan doc was corrected to match.
_ENCUMBERED_MULTIPLIER = 5
_HEAVILY_ENCUMBERED_MULTIPLIER = 10


def sheet_encumbrance(
    sheet: dict,
    catalog_weight_by_slug: "dict[str, str] | None" = None,
    effective_str: "int | None" = None,
) -> dict:
    """RAW PHB p.176 optional **Encumbrance variant**. Classifies the PC's
    current inventory weight into one of three tiers + the mechanical penalty
    each carries:

      - ``"heavily_encumbered"`` (weight > STR × 10): speed −20 ft AND
        disadvantage on STR/DEX/CON ability checks, attack rolls, and saving
        throws (``disadvantage_abilities = ["STR", "DEX", "CON"]``).
      - ``"encumbered"`` (weight > STR × 5): speed −10 ft.
      - ``"none"``: no penalty.

    **Derivation-only / informational.** The optional variant is a table
    opt-in, so this surfaces the tier on the sheet (via ``sheet_carry_summary``
    → ``/sheet-json``'s ``derived.carry``) for the player/GM to self-manage —
    it does NOT auto-install the speed-reduction / disadvantage buffs. Wiring
    the mechanical install (on the ``speed_reduction_ft`` substrate + the
    condition-disadvantage helpers) is a deferred follow-up that needs an
    inventory-change hook; see docs/plans/carrying-capacity.md Phase 4.

    Returns ``{tier, speed_penalty_ft, disadvantage_abilities}`` — always the
    same shape (``"none"`` carries a 0 penalty + empty list) so callers can
    read it unconditionally.
    """
    str_score = (
        effective_str if isinstance(effective_str, int)
        else _str_score_from_sheet(sheet)
    )
    str_score = max(1, str_score)
    weight = sheet_inventory_weight_lb(sheet, catalog_weight_by_slug)
    if weight > str_score * _HEAVILY_ENCUMBERED_MULTIPLIER:
        return {
            "tier": "heavily_encumbered",
            "speed_penalty_ft": 20,
            "disadvantage_abilities": ["STR", "DEX", "CON"],
        }
    if weight > str_score * _ENCUMBERED_MULTIPLIER:
        return {
            "tier": "encumbered",
            "speed_penalty_ft": 10,
            "disadvantage_abilities": [],
        }
    return {
        "tier": "none",
        "speed_penalty_ft": 0,
        "disadvantage_abilities": [],
    }


def sheet_carry_summary(
    sheet: dict,
    catalog_weight_by_slug: "dict[str, str] | None" = None,
    effective_str: "int | None" = None,
) -> dict:
    """Bundle the three derivations for ``/sheet-json``'s ``derived``
    response key. Keeps the route layer's wiring trivial.

    v2.212.0 — ``effective_str`` lets the route pass the override-folded
    STR (Belt of Giant Strength) so the carry meter reflects the boost."""
    cap = sheet_carry_capacity_lb(sheet, effective_str)
    weight = sheet_inventory_weight_lb(sheet, catalog_weight_by_slug)
    summary = {
        "carry_capacity_lb": cap,
        "inventory_weight_lb": weight,
        "is_over_capacity": weight > cap,
    }
    # v2.656.0 — Bag of Holding 500-lb capacity. Only surface the bag
    # fields when the PC actually has items stowed in a bag (else the
    # carry block stays clean for everyone else).
    inv = sheet.get("inventory") if isinstance(sheet, dict) else None
    has_bag = isinstance(inv, list) and any(
        isinstance(it, dict) and it.get("_in_bag_of_holding") for it in inv
    )
    if has_bag:
        bag_weight = sheet_bag_of_holding_weight_lb(sheet, catalog_weight_by_slug)
        summary["bag_of_holding_weight_lb"] = bag_weight
        summary["bag_of_holding_capacity_lb"] = BAG_OF_HOLDING_CAPACITY_LB
        summary["bag_of_holding_over_capacity"] = (
            bag_weight > BAG_OF_HOLDING_CAPACITY_LB
        )
    # v2.660.0 — Phase 4: encumbrance variant (PHB p.176). Only surface the
    # fields when the PC is actually encumbered, so the carry block stays
    # clean (3 fields) for the common unencumbered case — mirroring the
    # bag-of-holding fields above. The optional variant is informational
    # (player/GM self-manages); see ``sheet_encumbrance``.
    enc = sheet_encumbrance(sheet, catalog_weight_by_slug, effective_str)
    if enc["tier"] != "none":
        summary["encumbrance_tier"] = enc["tier"]
        summary["encumbrance_speed_penalty_ft"] = enc["speed_penalty_ft"]
        summary["encumbrance_disadvantage_abilities"] = enc[
            "disadvantage_abilities"
        ]
    return summary
