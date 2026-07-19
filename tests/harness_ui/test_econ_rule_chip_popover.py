"""v2.1032.0 — the 📖 SRD rules chip in the init-tracker econ strip.

The HTTP harness (`tests/harness/test_econ_rule_chip.py`) covers the
markup contract + that every slug the chip lists resolves against
`/api/reference/entry`. What it *can't* cover is the part that only
exists in the browser: the chip is rendered by `renderBattle`'s
template literal, and clicking it runs the generalized
`_openCondRefPopover` — the same function the ⚠ Conditions pill uses,
widened in this commit to read `data-ref-type` / `data-ref-slugs`.

That generalization is the risk this file guards. A regression in it
would break the *conditions* popover too, silently, since both paths
now share one function.

Seeding follows `test_legendary_action_buttons.py`: pre-bake the
battle into `localStorage` before load, using manual combatants (no
char_id / token_template_id) so the v2.25.1 orphan cleanup keeps them.
Battle is the GM's default-open right drawer in the demo, so no drawer
toggle is needed here.
"""
import json
import re

from playwright.sync_api import Page, expect

from .conftest import CAMPAIGN_ID, tabletop_url


_HERO_ID = "tok_hero_rulechip_test"


def _battle_json() -> str:
    return json.dumps({
        "combatants": [
            {
                "id": _HERO_ID,
                "char_id": None,
                "token_template_id": None,
                "name": "Rule Chip Tester",
                "initiative": 18,
                "hp_current": 22, "hp_max": 22,
                "buffs": [],
                "economy": {"action": False, "bonus": False,
                            "reaction": False, "movement": 0},
            },
        ],
        "turn_index": 0,
        "round": 1,
        "active": True,
    })


def _seed_battle(page: Page) -> None:
    page.add_init_script(
        f"window.localStorage.setItem('simplevtt_battle_{CAMPAIGN_ID}', "
        f"{json.dumps(_battle_json())});"
    )


def test_rule_chip_renders_in_econ_strip(gm_page: Page):
    """The 📖 chip renders inside the combatant's econ-chip strip,
    alongside the Act/Bns/Rxn/Mov chips."""
    _seed_battle(gm_page)
    gm_page.goto(tabletop_url())

    entry = gm_page.locator(f'.init-entry[data-char-id="{_HERO_ID}"]')
    expect(entry).to_be_visible(timeout=5000)

    chip = entry.locator(".econ-chips .rule-ref-chip")
    expect(chip).to_have_count(1)
    expect(chip).to_be_visible()
    expect(chip).to_have_attribute("data-ref-type", "rules")


def test_rule_chip_click_opens_srd_rules_popover(gm_page: Page):
    """Clicking the chip opens the shared reference popover carrying
    real SRD rule text fetched from `/api/reference/entry`."""
    _seed_battle(gm_page)
    gm_page.goto(tabletop_url())

    entry = gm_page.locator(f'.init-entry[data-char-id="{_HERO_ID}"]')
    expect(entry).to_be_visible(timeout=5000)
    entry.locator(".econ-chips .rule-ref-chip").click()

    pop = gm_page.locator("#cond-ref-popover")
    expect(pop).to_be_visible(timeout=5000)
    # Rules tier gets the neutral-accent modifier, not the conditions red.
    expect(pop).to_have_class(re.compile(r"is-rules"))
    # Real fetched SRD text, not the loading placeholder.
    expect(pop).to_contain_text("Dash", timeout=5000)
    expect(pop).to_contain_text("Dodge")
    expect(pop).not_to_contain_text("Loading SRD rules…")
    expect(pop.locator(".cond-ref-foot")).to_contain_text("CC BY 4.0")


def test_conditions_pill_popover_still_works(gm_page: Page):
    """Regression guard for the generalization itself.

    `_openCondRefPopover` was widened from conditions-only to
    type-aware in v2.1032.0. The ⚠ Conditions pill still emits the
    ORIGINAL `data-cond-slugs` attribute with no `data-ref-type`, so
    this exercises both back-compat paths at once: the type default
    ('conditions') and the slug-attribute fallback. If either broke,
    the pill would open an empty popover — and no HTTP test would
    notice, since the markup it asserts on is unchanged.

    The ⚠ pill only renders for a real PC (server-side, from
    `_mini_sheet_card.html`) or a monster-template combatant — not for
    the manual combatant this file seeds. Rather than reshape the
    fixture, we inject a pill carrying the legacy attribute and let the
    REAL delegated click handler drive the REAL popover function. That
    is precisely the contract under test: legacy attribute in, correct
    conditions lookup out.
    """
    _seed_battle(gm_page)
    gm_page.goto(tabletop_url())
    expect(gm_page.locator(f'.init-entry[data-char-id="{_HERO_ID}"]')
           ).to_be_visible(timeout=5000)

    gm_page.evaluate(
        """() => {
            const el = document.createElement('span');
            el.className = 'mini-ab-cond-warn';
            el.setAttribute('role', 'button');
            el.setAttribute('data-cond-slugs', 'poisoned');
            el.textContent = '\\u26a0 Conditions';
            el.id = 'legacy-pill-under-test';
            document.body.appendChild(el);
        }"""
    )
    gm_page.locator("#legacy-pill-under-test").click()

    pop = gm_page.locator("#cond-ref-popover")
    expect(pop).to_be_visible(timeout=5000)
    # Conditions tier → NOT the rules modifier, and real condition text.
    expect(pop).not_to_have_class(re.compile(r"is-rules"))
    expect(pop).to_contain_text("Poisoned", timeout=5000)
    expect(pop).not_to_contain_text("Loading SRD rules…")


def test_rule_chip_popover_dismisses(gm_page: Page):
    """Escape closes the popover (shared dismiss path with the ⚠ pill)."""
    _seed_battle(gm_page)
    gm_page.goto(tabletop_url())

    entry = gm_page.locator(f'.init-entry[data-char-id="{_HERO_ID}"]')
    expect(entry).to_be_visible(timeout=5000)
    entry.locator(".econ-chips .rule-ref-chip").click()
    expect(gm_page.locator("#cond-ref-popover")).to_be_visible(timeout=5000)

    gm_page.keyboard.press("Escape")
    expect(gm_page.locator("#cond-ref-popover")).to_have_count(0)
