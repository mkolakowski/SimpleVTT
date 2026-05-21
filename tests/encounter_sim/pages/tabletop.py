"""Page object for the tabletop / campaign view.

Centralizes selectors so a DOM change shows up as one file diff
instead of N test failures. See ``docs/plans/encounter-sim-test-
suite.md``'s "Design principles" section for the rationale.

The class is a thin shell today (commit B of Phase 1) — methods
land alongside the first encounter-sim test in commit C as that
test discovers what it needs. Resist adding speculative method
stubs; add them when a test imports them.

Intended surface (from the plan):
  - ``goto()``                              navigate to the tabletop view
  - ``drag_token(name, dx, dy)``           drag a token by name
  - ``click_token(name)``                  select a combatant
  - ``open_sheet(name)``                   open the full sheet drawer
  - ``get_combatant_row(name) -> Locator`` init-tracker row by name
  - ``read_hp(name) -> tuple[int, int]``   (current, max) from the row
"""
from __future__ import annotations

from playwright.sync_api import Page


class TabletopPage:
    def __init__(self, page: Page) -> None:
        self.page = page
