"""v2.1044.1 — opening a monster's full stat block from its init-tracker row.

Two behaviors ship here, and both only exist in the browser (the HTTP
harness can't see either — `renderBattle` builds the row from a template
literal client-side, and the drawer is pure DOM):

1. **Double-click a monster row → the stat-block drawer opens**, matching
   the map token's double-click-to-open. Crucially the single-click inline
   expand is *preserved*, so this had to leave the existing toggle intact —
   the double-click handler explicitly undoes the toggle the first click of
   the pair already applied.
2. **An orphan row opens the sheet on the FIRST click**, because expanding
   it would only reveal the "Template missing — open the full monster sheet
   via the 📋 button above" placeholder, i.e. a dead end pointing at another
   button.

The regression this file really guards is #1's interaction with the
pre-existing expand: it would be easy to ship a double-click that leaves
rows randomly expanded or collapsed, and nothing else would catch it.

**Fixture note.** The battle is seeded into `localStorage` (same pattern as
`test_econ_rule_chip_popover.py`), but unlike that file this one needs a
combatant with a REAL `token_template_id` — the v2.25.1 orphan cleanup at
`tabletop.html:~8242` drops any combatant whose template isn't on a current
token. So the template + its token are resolved at runtime from the page's
`#initial-data` payload rather than hardcoded, per the by-name mandate in
CLAUDE.md (hardcoded ids drift across demo reseeds — the B18-class-6 /
v2.1033.16 lesson).
"""
from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import Page, expect

from .conftest import CAMPAIGN_ID, tabletop_url


_COMBATANT_ID = "tok_monster_row_sheet_test"


def _resolve_monster(page: Page) -> dict:
    """Pick a monster template that is actually placed on the active map.

    Returns {tid, name}. Resolved from `#initial-data` in the live page so
    a demo reseed (which cycles template ids) can't stale this test.
    """
    page.goto(tabletop_url())
    data = page.evaluate(
        """() => {
            const el = document.getElementById('initial-data');
            if (!el) return null;
            const d = JSON.parse(el.textContent || '{}');
            const tok = (d.tokens || []).find(t => t.token_template_id);
            if (!tok) return null;
            const tmpl = (d.templates || [])
                .find(t => t.id === tok.token_template_id);
            return { tid: tok.token_template_id, name: (tmpl || {}).name || '' };
        }"""
    )
    if not data or not data.get("tid"):
        pytest.skip("demo has no monster token on the active map to drive this test")
    return data


def _seed_and_load(page: Page, tid: int) -> None:
    battle = json.dumps({
        "combatants": [
            {
                "id": _COMBATANT_ID,
                "char_id": None,
                "token_template_id": tid,
                "name": "Row Sheet Tester",
                "initiative": 17,
                "hp_current": 15, "hp_max": 15,
                "buffs": [],
                "economy": {"action": False, "bonus": False,
                            "reaction": False, "movement": 0},
            },
        ],
        "turn_index": 0,
        "round": 1,
        # active=False on purpose. With an ACTIVE battle the GM
        # auto-expand-on-turn-change (`_lastAutoExpandedIdx`, tabletop.html
        # ~:10280) expands the active combatant's row during render, so every
        # row here would start open and the expand-state assertions below
        # would be measuring that, not the click handlers.
        "active": False,
    })
    page.add_init_script(
        f"window.localStorage.setItem('simplevtt_battle_{CAMPAIGN_ID}', "
        f"{json.dumps(battle)});"
    )
    page.goto(tabletop_url())


def _row(page: Page, tid: int):
    return page.locator(f'.init-entry[data-monster-tid="{tid}"]')


def _expect_drawer_open(page: Page, opened: bool) -> None:
    """Assert the stat-block drawer's open/closed state.

    Deliberately NOT `expect('#monster-sheet-drawer').to_be_visible()`. That
    element's inline style at `tabletop.html:~6002` sets BOTH `display:none`
    and `display:flex` — the later declaration wins, so the drawer is *always*
    "visible" to Playwright and is only actually hidden by
    `transform: translateX(100%)`. A `to_be_visible()` assertion there passes
    trivially and proves nothing (it silently no-op'd an earlier draft of this
    file). The backdrop is the honest signal: `openDrawer` flips it to
    `display:block`, `closeDrawer` back to `none`.
    """
    backdrop = page.locator("#monster-sheet-backdrop")
    if opened:
        expect(backdrop).to_be_visible(timeout=5000)
        # ...and the iframe is actually pointed at a monster stat block.
        expect(page.locator("#monster-sheet-drawer-iframe")).to_have_attribute(
            "src", re.compile(r"/monster-template/\d+/sheet"), timeout=5000
        )
    else:
        expect(backdrop).to_be_hidden()


def _header(row):
    """The safe click target inside the row header.

    NOT `.mini-header` itself — its centre lands on the econ-chip strip
    (Act/Bns/Rxn/Mov are real <button>s), and both handlers deliberately
    bail on `closest('input, button, a')`, so a centre-click would be a
    silent no-op. The name element is inert and bubbles to both the
    header's expand listener and the row's dblclick listener.
    """
    return row.locator(".mini-header-name")


def test_monster_row_is_stamped_with_template_id(gm_page: Page):
    """The row carries data-monster-tid so the click handlers can find the
    sheet without re-deriving the URL."""
    info = _resolve_monster(gm_page)
    _seed_and_load(gm_page, info["tid"])

    row = _row(gm_page, info["tid"])
    expect(row).to_have_count(1, timeout=5000)
    expect(row).to_be_visible()
    # The 📋 anchor the handlers synthesize a click on must be present.
    expect(row.locator("a.monster-sheet-link")).to_have_count(1)


def test_single_click_still_expands_inline_and_does_not_open_drawer(gm_page: Page):
    """The pre-existing behavior must survive: one click expands the inline
    mini-sheet and does NOT open the drawer."""
    info = _resolve_monster(gm_page)
    _seed_and_load(gm_page, info["tid"])

    row = _row(gm_page, info["tid"])
    expect(row).to_be_visible(timeout=5000)
    sheet = row.locator(".init-card-sheet")
    assert "open" not in (sheet.get_attribute("class") or "")

    _header(row).click()
    expect(sheet).to_have_class(re.compile(r"\bopen\b"), timeout=3000)

    _expect_drawer_open(gm_page, False)


def test_double_click_opens_sheet_drawer_and_preserves_expand_state(gm_page: Page):
    """Double-click opens the stat block, and leaves the row's expand state
    exactly as it found it (the handler undoes the first click's toggle)."""
    info = _resolve_monster(gm_page)
    _seed_and_load(gm_page, info["tid"])

    row = _row(gm_page, info["tid"])
    expect(row).to_be_visible(timeout=5000)
    sheet = row.locator(".init-card-sheet")
    before = "open" in (sheet.get_attribute("class") or "")

    _header(row).dblclick()

    _expect_drawer_open(gm_page, True)

    gm_page.wait_for_timeout(300)
    after = "open" in (sheet.get_attribute("class") or "")
    assert after == before, (
        f"double-click changed the expand state (before={before}, after={after}); "
        "the toggle-undo in the dblclick handler regressed"
    )


def test_orphan_row_opens_sheet_on_first_click(gm_page: Page):
    """An orphan row skips the dead-end expand and goes straight to the sheet.

    `_activate` reads `entry.dataset.monsterOrphan` at CLICK time, so setting
    the attribute post-render exercises the real handler on a real row — the
    same injection technique `test_econ_rule_chip_popover.py` uses for the
    legacy conditions pill. Seeding a genuinely-orphaned combatant isn't
    possible here: the v2.25.1 cleanup culls any combatant whose template
    isn't on a live token before render.
    """
    info = _resolve_monster(gm_page)
    _seed_and_load(gm_page, info["tid"])

    row = _row(gm_page, info["tid"])
    expect(row).to_be_visible(timeout=5000)
    sheet = row.locator(".init-card-sheet")

    row.evaluate("el => el.dataset.monsterOrphan = '1'")
    _header(row).click()

    _expect_drawer_open(gm_page, True)
    # And it must NOT have expanded the dead-end card on the way.
    assert "open" not in (sheet.get_attribute("class") or ""), (
        "orphan row expanded its placeholder card instead of going straight "
        "to the sheet"
    )
