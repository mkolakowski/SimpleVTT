"""Visual baselines for the major roll-log card types.

Companion to test_visual_spell_card.py — the spell card was the
v2.97.13 proof-of-concept; this file extends coverage to the rest of
the roll-log family:

  - .roll-card — basic d20 result (the bread-and-butter dice roll)
  - .weapon-atk-card — weapon attack (hit + damage breakdown)
  - .feature-used-card — class-feature use with v2.96.0 ↶ Undo pill

Each test injects a synthetic ``<li>`` directly into ``#roll-list`` so
the production CSS picks it up, then captures a screenshot. First run
captures baseline; subsequent runs diff against it (1 % default
threshold). Refresh baselines after intentional visual changes:

    pytest tests/harness_ui/test_visual_roll_log_cards.py --update-snapshots

Card markup mirrors what the v2.97.13 tabletop.js renderers produce —
not a perfect 1:1 (the JS reads varied client state like portraits,
USER_COLORS, _CAMPAIGN_ID); the inlined HTML uses safe defaults that
exercise the CSS without depending on that state.
"""
import pytest
from playwright.sync_api import Page, expect

from .conftest import assert_visual_match, disable_animations, tabletop_url


_ROLL_CARD_HTML = """
<li>
  <div class="roll-card">
    <div class="roll-card-total-col">
      <span class="roll-card-total">18</span>
    </div>
    <div class="roll-card-right">
      <div class="roll-card-header">
        <div class="roll-card-avatar">🎲</div>
        <span class="roll-card-user">Pip Quickfingers</span>
        <span class="roll-card-time">10:42 AM</span>
      </div>
      <div class="roll-card-body">
        <div class="roll-card-note">Stealth check</div>
        <div class="result-pills">
          <span class="result-pill">🎲 1d20+5 → (13)+5 = 18</span>
        </div>
      </div>
    </div>
  </div>
</li>
"""


_WEAPON_ATTACK_CARD_HTML = """
<li data-attack-id="visual-test-strike">
  <div class="spell-cast-card weapon-atk-card">
    <div class="roll-card-header">
      <div class="roll-card-avatar">🪄</div>
      <span class="roll-card-user">Garrik Ironside</span>
      <span class="spell-cast-slot">⚔ Attack</span>
      <span class="roll-card-time">10:42 AM</span>
    </div>
    <div class="spell-cast-body">
      <div class="spell-cast-name-row">
        <span class="spell-cast-name">🗡 Greatsword</span>
        <span class="spell-cast-meta-inline">· slashing</span>
      </div>
      <div class="result-pills">
        <span class="result-pill chip-hit">🎯 Hit (18 vs AC 15)</span>
        <span class="result-pill chip-damage">⚔ 9 slashing</span>
        <button type="button" class="result-pill chip-undo weapon-atk-undo">↶ Undo</button>
      </div>
    </div>
  </div>
</li>
"""


_FEATURE_USED_CARD_HTML = """
<li>
  <div class="roll-card feature-used-card">
    <div class="roll-card-header">
      <div class="roll-card-avatar">✨</div>
      <span class="roll-card-user">Sir Caelan Lightbringer</span>
      <span class="spell-cast-slot">Class Feature</span>
      <span class="roll-card-time">10:42 AM</span>
    </div>
    <div class="roll-card-body" style="padding:6px 10px 8px;">
      <div class="feature-used-name-row">
        <strong class="feature-used-name">🛡 Lay on Hands</strong>
        <span class="feature-used-desc">Healed Pip Quickfingers for 5 HP</span>
        <span class="feature-used-counter">30/35</span>
      </div>
      <div class="result-pills">
        <button type="button" class="result-pill chip-undo feature-cast-undo">↶ Undo</button>
      </div>
    </div>
  </div>
</li>
"""


_CARD_FIXTURES = {
    "roll_card_basic": _ROLL_CARD_HTML,
    "weapon_attack_card_hit": _WEAPON_ATTACK_CARD_HTML,
    "feature_used_card_with_undo": _FEATURE_USED_CARD_HTML,
}


def _open_roll_log(page: Page) -> None:
    """Make sure the roll-log drawer is open before we inject."""
    drawer = page.locator("#roll-log-drawer")
    if drawer.count() and not drawer.is_visible():
        tab = page.locator('button[data-target="roll-log-drawer"]').first
        if tab.count():
            try:
                tab.click(timeout=1500)
                drawer.wait_for(state="visible", timeout=2000)
            except Exception:
                pass


def _inject_card(page: Page, html: str) -> None:
    page.evaluate(
        """(html) => {
            const list = document.getElementById('roll-list');
            if (!list) throw new Error('roll-list not in DOM');
            list.innerHTML = '';
            list.insertAdjacentHTML('beforeend', html);
        }""",
        html,
    )


@pytest.mark.parametrize("name", list(_CARD_FIXTURES.keys()))
def test_visual_roll_log_card(
    gm_page: Page, update_snapshots: bool, name: str
) -> None:
    """Captures a baseline screenshot of the named card type. First
    run writes the baseline; subsequent runs assert no >1% pixel
    drift. See `docs/wiki/visual-regression-harness.md` for the
    workflow + cross-machine determinism caveats.
    """
    gm_page.set_viewport_size({"width": 1280, "height": 800})
    response = gm_page.goto(tabletop_url())
    assert response is not None and response.ok, (
        f"tabletop load failed: {response.status if response else 'no response'}"
    )

    _open_roll_log(gm_page)
    _inject_card(gm_page, _CARD_FIXTURES[name])

    # The first <li> in #roll-list is the one we just inserted.
    card = gm_page.locator("#roll-list > li").first
    expect(card).to_be_visible(timeout=3000)

    disable_animations(gm_page)
    assert_visual_match(card, name, update=update_snapshots)
