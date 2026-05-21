"""Page object for the roll-log drawer (``#roll-log-drawer``).

See ``docs/plans/encounter-sim-test-suite.md``. Thin shell today;
methods land in commit C as ``test_garrik_strike.py`` exercises them.

Intended surface (from the plan):
  - ``cards() -> Locator``                       all .roll-card elements
  - ``find_card_by_cast_id(cast_id) -> Locator`` lookup by data-cast-id
  - ``find_card_by_action(name) -> Locator``     newest card with header
                                                 text matching ``name``
  - ``expand(card)``                             click to expand details
"""
from __future__ import annotations

from playwright.sync_api import Page


class RollLogPage:
    def __init__(self, page: Page) -> None:
        self.page = page
