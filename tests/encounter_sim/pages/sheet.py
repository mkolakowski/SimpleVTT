"""Page object for the character-sheet view (``/campaign/<cid>/
character/<id>/sheet``).

See ``docs/plans/encounter-sim-test-suite.md`` for the rationale.
Thin shell today (commit B); methods grow in commit C as
``test_garrik_strike.py`` discovers what it needs.

Intended surface (from the plan):
  - ``goto(char_id)``                              navigate
  - ``click_attack_strike(weapon_name)``           click .atk-strike for a row
  - ``click_attack_roll(weapon_name)``             click .atk-roll for a row
  - ``click_cast_spell(spell_name)``               click .sp-cast
  - ``read_hp() -> tuple[int, int]``               (#hp-current-input, #hp-max)
  - ``read_buff_list() -> list[str]``              names of installed buffs
"""
from __future__ import annotations

from playwright.sync_api import Page


class SheetPage:
    def __init__(self, page: Page) -> None:
        self.page = page
