"""Visual-regression smoke tests for the v2.97.12 spell-card pillification.

Two states captured:
  - ``spell_card_collapsed``: meta pill row + .result-pills + actions,
    description pill in its closed state.
  - ``spell_card_expanded``: same card after clicking the description
    pill's summary so the .spell-meta-pill-body is visible inline.

How it works:
  1. Navigate to the tabletop as the GM.
  2. Inject a synthetic ``<li>`` into the roll-list with the exact
     markup ``appendSpellCast()`` would produce for a sample Fireball
     cast. The CSS for ``.spell-meta-pill`` / ``.spell-cast-card``
     etc. is the actual production stylesheet so the screenshot
     reflects the real rendered card.
  3. Disable animations + take a screenshot of the ``<li>`` element.
  4. Open the description pill and capture a second screenshot.

Updating baselines (intentional visual changes):
    pytest tests/harness_ui/test_visual_spell_card.py --update-snapshots

CI note: this test is local-only today. Mac-vs-Linux font / AA jitter
would noise the diff in CI. See ``conftest.py`` for the rationale.
"""
import pytest
from playwright.sync_api import Page, expect

from .conftest import assert_visual_match, disable_animations, tabletop_url


# Synthetic spell-card markup matching exactly what ``appendSpellCast``
# in tabletop.js produces for a Fireball cast. Kept inline here so the
# baseline doesn't depend on a server-side cast (which would require a
# WS round-trip + roster lookup). When the JS shape changes, update
# this fixture AND re-capture baselines.
_SAMPLE_FIREBALL_LI_HTML = """
<li data-cast-id="visual-test-fireball">
  <div class="spell-cast-card">
    <div class="roll-card-header">
      <div class="roll-card-avatar">🪄</div>
      <span class="roll-card-user">Zara Emberfire</span>
      <span class="spell-cast-slot">Lv 3 slot</span>
      <span class="roll-card-time">10:42 AM</span>
    </div>
    <div class="spell-cast-body">
      <div class="spell-cast-name-row">
        <span class="spell-cast-name">🪄 Fireball</span>
      </div>
      <div class="spell-meta-pills">
        <span class="spell-meta-pill">Evocation</span>
        <span class="spell-meta-pill">⏱ 1 action</span>
        <span class="spell-meta-pill">📏 150 ft</span>
        <details class="spell-meta-pill" data-visual-test-details>
          <summary>details</summary>
          <div class="spell-meta-pill-body">A bright streak flashes from your pointing finger to a point you choose within range and then blossoms with a low roar into an explosion of flame.</div>
        </details>
      </div>
      <div class="spell-cast-actions"></div>
    </div>
  </div>
</li>
"""


def _inject_sample_card(page: Page) -> None:
    """Drop the sample spell card into ``#roll-list`` so the real
    CSS picks it up. Asserts the roll-list exists first so a missed
    selector / DOM regression surfaces clearly."""
    page.evaluate(
        """(html) => {
            const list = document.getElementById('roll-list');
            if (!list) throw new Error('roll-list not in DOM');
            list.innerHTML = '';
            list.insertAdjacentHTML('beforeend', html);
        }""",
        _SAMPLE_FIREBALL_LI_HTML,
    )


def _open_roll_log_if_collapsed(page: Page) -> None:
    """The roll log lives in #roll-log-drawer which may be collapsed
    on first load. Click the "Roll Log" tab button to open it."""
    drawer = page.locator("#roll-log-drawer")
    if drawer.count() and not drawer.is_visible():
        tab = page.locator('button[data-target="roll-log-drawer"]').first
        if tab.count():
            try:
                tab.click(timeout=1500)
            except Exception:
                pass
            # Give the drawer the open transition some time to land.
            try:
                drawer.wait_for(state="visible", timeout=2000)
            except Exception:
                pass


@pytest.mark.parametrize("state", ["collapsed", "expanded"])
def test_visual_spell_card_pillification(
    gm_page: Page, update_snapshots: bool, state: str
) -> None:
    """Captures the spell-card render in both collapsed (details closed)
    and expanded (details summary clicked) states. First run captures
    baselines; subsequent runs assert no >1% pixel drift."""
    gm_page.set_viewport_size({"width": 1280, "height": 800})
    response = gm_page.goto(tabletop_url())
    assert response is not None and response.ok, (
        f"tabletop load failed: {response.status if response else 'no response'}"
    )

    _open_roll_log_if_collapsed(gm_page)
    _inject_sample_card(gm_page)

    card = gm_page.locator('li[data-cast-id="visual-test-fireball"]').first
    expect(card).to_be_visible(timeout=3000)

    if state == "expanded":
        gm_page.locator(
            'details.spell-meta-pill[data-visual-test-details] > summary'
        ).first.click()
        # Confirm the body actually flipped to visible before snapshot.
        expect(
            gm_page.locator(
                'details.spell-meta-pill[data-visual-test-details] '
                '> .spell-meta-pill-body'
            )
        ).to_be_visible()

    disable_animations(gm_page)
    assert_visual_match(
        card,
        f"spell_card_{state}",
        update=update_snapshots,
    )
