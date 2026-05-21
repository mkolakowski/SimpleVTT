"""Page object for the tabletop / campaign view.

Centralizes selectors so a DOM change shows up as one file diff
instead of N test failures. See ``docs/plans/encounter-sim-test-
suite.md``'s "Design principles" section for the rationale.

Methods land here as tests grow into them — first PoC
(``test_garrik_strike``) needs ``goto`` + ``combatant_row`` +
``combatant_hp`` for the init-tracker HP-drop assertion. More land
as Phase 1 commits C and D add Tavik and Thalindra.
"""
from __future__ import annotations

import os

from playwright.sync_api import Locator, Page


BASE_URL = os.getenv("HARNESS_BASE_URL", "http://localhost:8013")
CAMPAIGN_ID = int(os.getenv("HARNESS_TEST_CAMPAIGN", "1"))


class TabletopPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def goto(self) -> None:
        """Navigate to ``/campaign/<CAMPAIGN_ID>``. Must be called
        AFTER WSCollector.start() if the test needs the initial
        ``battle_update`` frame on connect.
        """
        self.page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")

    def combatant_row(self, name: str) -> Locator:
        """Locator for the ``.init-entry`` whose mini-header name
        matches. Returns the first match — combatant names are unique
        per battle in practice."""
        return self.page.locator(".init-entry").filter(
            has=self.page.locator(".mini-header-name", has_text=name)
        ).first

    def combatant_hp(self, name: str) -> int:
        """Current HP for the named combatant, read from the
        ``.init-hp-cur`` input that the GM view renders inside the
        expanded init-entry.

        Caveat: ``.init-hp-cur`` is only present on the GM view
        (``editRow`` in tabletop.html:5003). Player view falls back
        to parsing ``.mini-header-sub``; we don't support that yet
        because Phase 1 tests run as GM.
        """
        row = self.combatant_row(name)
        hp_input = row.locator(".init-hp-cur").first
        return int(hp_input.input_value())
