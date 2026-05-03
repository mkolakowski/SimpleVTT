"""Known game systems and their per-system tabletop behavior.

Adding a new system: register a `GameSystem` with a unique key, the matching
character sheet template name (must exist in `sheet_templates.py` and the
templates directory as `sheet_<template>.html`), the display label, and the
quick-die buttons that should appear in the dice tray.

A campaign's `game_system` field stores the key. The whole UI keys off this:
the tabletop renders the system badge, the sheet modal picks the matching
template, the dice tray renders system-specific shortcuts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class QuickDie:
    label: str
    expression: str  # any expression understood by app/dice.py


@dataclass(frozen=True)
class GameSystem:
    key: str
    label: str
    sheet_template: str  # matches the `template` field on Character + sheet_<x>.html
    quick_dice: List[QuickDie] = field(default_factory=list)
    # When True, the sheet for this system supports auto-rolls (clicking a
    # skill/save/ability fires a roll with the right modifier). The frontend
    # checks this flag via campaign.game_system.
    rollable_sheet: bool = False


_GENERIC_QUICK = [
    QuickDie("d4", "1d4"),
    QuickDie("d6", "1d6"),
    QuickDie("d8", "1d8"),
    QuickDie("d10", "1d10"),
    QuickDie("d12", "1d12"),
    QuickDie("d20", "1d20"),
    QuickDie("d100", "1d100"),
]

_DND5E_QUICK = [
    QuickDie("d20", "1d20"),
    QuickDie("adv", "1d20a"),
    QuickDie("dis", "1d20d"),
    QuickDie("d4", "1d4"),
    QuickDie("d6", "1d6"),
    QuickDie("d8", "1d8"),
    QuickDie("d10", "1d10"),
    QuickDie("d12", "1d12"),
    QuickDie("4d6kh3", "4d6kh3"),  # ability score generation
]


SYSTEMS: Dict[str, GameSystem] = {
    "generic": GameSystem(
        key="generic",
        label="Generic / system-agnostic",
        sheet_template="generic",
        quick_dice=_GENERIC_QUICK,
        rollable_sheet=False,
    ),
    "dnd5e": GameSystem(
        key="dnd5e",
        label="Dungeons & Dragons 5e",
        sheet_template="dnd5e",
        quick_dice=_DND5E_QUICK,
        rollable_sheet=True,
    ),
}


def get_system(key: str) -> GameSystem:
    """Return the GameSystem for a key, falling back to generic."""
    return SYSTEMS.get((key or "").lower(), SYSTEMS["generic"])


def system_choices() -> List[GameSystem]:
    """Order matters: generic first, then alphabetical by label."""
    rest = sorted(
        (s for k, s in SYSTEMS.items() if k != "generic"),
        key=lambda s: s.label,
    )
    return [SYSTEMS["generic"], *rest]
