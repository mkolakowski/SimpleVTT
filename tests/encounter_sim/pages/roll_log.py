"""Page object for the roll-log drawer (``#roll-log-drawer`` →
``#roll-list``).

Thin shell that grows as tests need it. v2.49.16 PoC needs only
``latest_weapon_attack_card`` for the Garrik strike assertion;
Tavik / Thalindra in commit D will add ``latest_spell_cast_card``.
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page


class RollLogPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def latest_weapon_attack_card(self) -> Locator:
        """The newest weapon-attack card in the roll-log drawer.

        The card DOM is rendered by ``tabletop.js`` at line ~3547 —
        an ``<li>`` containing ``<div class="spell-cast-card
        weapon-atk-card">``. The list lives at ``#roll-list``. The
        ``.last`` locator picks the most recent, which is enough for
        single-action tests; multi-action tests should snapshot
        ``card.count()`` first and slice off the new ones.
        """
        return self.page.locator("#roll-list .weapon-atk-card").last

    def latest_spell_cast_card(self) -> Locator:
        """The newest spell-cast card in the roll-log drawer.

        Rendered by ``tabletop.js::appendSpellCast`` (line ~2780) —
        an ``<li>`` containing ``<div class="spell-cast-card">``
        (without the ``.weapon-atk-card`` modifier). The :not(...)
        filter excludes the weapon-attack cards, which carry both
        classes; without it, the newest matching element could be a
        Greatsword card from a co-located test, not the spell card
        we just cast.
        """
        return self.page.locator(
            "#roll-list .spell-cast-card:not(.weapon-atk-card)"
        ).last
