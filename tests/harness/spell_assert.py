"""Assertion helpers for the spell-validation suite.

Companion to ``spell_catalog.py``. The per-mechanic catalog tests
(Phase 2A damage, 2B save, 2C attack, 2D heal, …) call these
helpers so failure messages stay consistent + diagnostic. Each
helper prints the catalog slug + the expected vs observed value
so a CI failure points directly at the content edit that broke
the contract.
"""
from __future__ import annotations

from .spell_catalog import dice_range


def assert_damage_in_range(
    damage_total: int,
    expression: str,
    *,
    spell_name: str = "?",
    slot_level: int | None = None,
    upcast_dice: str = "",
) -> None:
    """Assert ``damage_total`` falls inside the (min, max) range of
    the dice expression. ``upcast_dice`` is concatenated to the base
    expression when present so leveled spells (Magic Missile +1 dart
    per slot, Fireball +1d6 per slot above 3rd, etc.) can extend the
    bounds without rebuilding the expression at the call site.

    Failure message format puts the spell + expression + slot up
    front so a CI log shows the failed spell first.
    """
    full_expr = (expression or "").strip()
    if upcast_dice:
        upcast_dice = upcast_dice.strip()
        if upcast_dice and not upcast_dice.startswith(("+", "-")):
            upcast_dice = "+" + upcast_dice
        full_expr = full_expr + upcast_dice
    lo, hi = dice_range(full_expr)
    assert lo <= damage_total <= hi, (
        f"{spell_name}: damage_total={damage_total} not in [{lo}, {hi}] "
        f"for expression {full_expr!r}"
        + (f" (slot L{slot_level})" if slot_level is not None else "")
    )
