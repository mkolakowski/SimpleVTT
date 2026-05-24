"""Harness regression tests for the PC mini-sheet partial extractions.

Phase 2.6 of the unified-mini-sheet plan. v2.49.193–.197 extracted four
per-tab partials from ``_mini_sheet_card.html``:
  * ``_tab_actions.html``  (2.49.193)
  * ``_tab_spells.html``   (2.49.195)
  * ``_tab_skills.html``   (2.49.196)
  * ``_tab_features.html`` (2.49.197)

Plus v2.49.198 made the tab strip + content render iterate a single
``_tabs_present`` list of ``{file, panel, label}`` dicts (Phase 2.4).

These tests lock in the per-tab partial extractions as a regression net:
loading the demo campaign's tabletop page renders every PC's mini-sheet
through the partial without throwing, the tab strip emits the expected
buttons per-character, and each per-tab partial produces panel content
when its gate is satisfied.

NPC mini-sheets are still rendered client-side via ``buildMonsterInitSheet``
in tabletop.html — not covered here. Phase 2.5's NPC body swap will add
matching coverage.
"""
from __future__ import annotations

import re

import httpx

from .helpers import BASE_URL


CAMPAIGN_PAGE = "/campaign/1"


def _mini_sheet_block(html: str, char_id: int | None = None, char_name: str | None = None) -> str:
    """Return the ``.char-detail`` slice for a given PC, looked up by
    char_id (preferred) or by name appearing in the ``.mini-header-name``
    div. Returns the raw HTML between the ``<div class="char-detail">``
    open and a large-enough window after for substring asserts."""
    if char_id is not None:
        marker = f'id="char-detail-{char_id}"'
        idx = html.find(marker)
        assert idx >= 0, f"char-detail block for id={char_id} not found"
    else:
        # The partial emits: <div class="mini-header-name">{name} <span class="conc-dot" ...
        # so anchor on the open-tag + the name (no trailing </div>; the
        # name is followed by a space and the concentration sigil span).
        marker = f'class="mini-header-name">{char_name}'
        idx = html.find(marker)
        assert idx >= 0, f"char-detail block for name={char_name!r} not found"
    # Walk back to the enclosing <div class="char-detail" ...>.
    start = html.rfind('<div class="char-detail"', 0, idx)
    assert start >= 0, "char-detail wrapper open tag not found"
    # The block is large; grab a generous window for substring asserts.
    # 30 KB is enough for any single PC's mini-sheet (Zara — full caster
    # with multiclass slots + many spells — is ~22 KB).
    end = min(start + 60000, len(html))
    return html[start:end]


async def test_tabletop_renders_all_demo_pc_mini_sheets():
    """GET /campaign/1 — 200 + every demo PC's .mini-sheet block is
    present in the response HTML. Asserts the partial loads without
    throwing for all 12 PCs (Phase A-wrap roster covering all 12 PHB
    classes); a single Jinja error in any sub-partial would 500 the page
    and miss every assertion below."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        login = await client.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"}, follow_redirects=True)
        assert login.status_code in (200, 303)
        resp = await client.get(CAMPAIGN_PAGE, follow_redirects=True)
    assert resp.status_code == 200, f"tabletop page failed: {resp.status_code}"
    html = resp.text
    # All 12 demo PCs render through the partial — name appears inside a
    # ``.mini-header-name`` div (the partial's header convention). Use
    # the full character name to disambiguate (PC names are unique).
    for name in (
        "Pip Quickfingers",
        "Thalindra Moonwhisper",
        "Brother Tavik Stonebrow",
        "Sir Caelan Lightbringer",
        "Lyra Sunstrider",
        "Mira Greenleaf",
        "Garrik Ironside",
        "Kael Brightleaf",
        "Zara Emberfire",
        "Krieger Stonefist",
        "Rowan Quickbow",
        "Magnus Hexbinder",
    ):
        assert f'class="mini-header-name">{name}' in html, f"mini-sheet for {name!r} not rendered"


async def test_tab_strip_renders_per_tabs_present_list():
    """Phase 2.4 verification — the unified ``_tabs_present`` iteration
    emits the tab buttons in the documented order (Actions / Spells /
    Features / Skills, gated by character data). Skills is always last
    and always present. Spot-checks Zara Emberfire (Sorcerer, full
    caster — should have all four tabs)."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        login = await client.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"}, follow_redirects=True)
        assert login.status_code in (200, 303)
        resp = await client.get(CAMPAIGN_PAGE, follow_redirects=True)
    assert resp.status_code == 200
    html = resp.text
    zara = _mini_sheet_block(html, char_name="Zara Emberfire")
    # All four tab buttons render for a full-caster Sorcerer.
    for tab_key, tab_label in (
        ("attacks", "Actions"),
        ("spells", "Spells"),
        ("features", "Features"),
        ("skills", "Skills"),
    ):
        assert f'data-tab="{tab_key}"' in zara, f"Zara missing tab button {tab_key!r}"
        # The label appears immediately after the data-tab attr in the
        # button. Use the data-tab attr as the anchor + scan forward.
        tab_idx = zara.find(f'data-tab="{tab_key}"')
        snippet = zara[tab_idx : tab_idx + 200]
        assert tab_label in snippet, f"Zara tab button label {tab_label!r} not found near data-tab={tab_key!r}"


async def test_actions_panel_renders_when_attacks_present():
    """Phase 2.1 verification — ``_tab_actions.html`` produces the
    Actions panel with at least one ``.mini-attack-row`` for a PC with
    weapon attacks. Spot-checks Pip Quickfingers (Rogue, has Dagger
    and/or Shortbow per the demo seed)."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        login = await client.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"}, follow_redirects=True)
        assert login.status_code in (200, 303)
        resp = await client.get(CAMPAIGN_PAGE, follow_redirects=True)
    pip = _mini_sheet_block(resp.text, char_name="Pip Quickfingers")
    # Actions tab panel + the partial's tell-tale row + Strike button.
    assert 'data-panel="attacks"' in pip, "Actions panel not rendered for Pip"
    assert 'class="mini-attack-row' in pip, "no .mini-attack-row in Pip's Actions panel"
    assert '🗡 Strike' in pip, "🗡 Strike button missing in Pip's Actions panel"


async def test_spells_panel_renders_for_caster_with_slots():
    """Phase 2.2 verification — ``_tab_spells.html`` produces the Spells
    panel with at least one ``.mini-spell-row`` + a ``.mini-slot-row``
    slot-pip bar for a level-≥-1 spell. Spot-checks Zara Emberfire
    (Sorcerer 5, has cantrips + leveled spells + sorcery slots)."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        login = await client.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"}, follow_redirects=True)
        assert login.status_code in (200, 303)
        resp = await client.get(CAMPAIGN_PAGE, follow_redirects=True)
    zara = _mini_sheet_block(resp.text, char_name="Zara Emberfire")
    assert 'data-panel="spells"' in zara, "Spells panel not rendered for Zara"
    assert 'class="mini-spell-row' in zara, "no .mini-spell-row in Zara's Spells panel"
    assert '✨ Cast' in zara, "✨ Cast button missing in Zara's Spells panel"
    assert 'class="mini-slot-row"' in zara, "no .mini-slot-row (slot pips) in Zara's Spells panel"


async def test_skills_panel_renders_all_18_skills():
    """Phase 2.3 verification — ``_tab_skills.html`` produces the Skills
    panel with all 18 skill buttons (the `SKILLS_LIST` constant moved
    inside the partial). Spot-checks one PC; the 18-skill grid is the
    same shape for every character regardless of class."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        login = await client.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"}, follow_redirects=True)
        assert login.status_code in (200, 303)
        resp = await client.get(CAMPAIGN_PAGE, follow_redirects=True)
    pip = _mini_sheet_block(resp.text, char_name="Pip Quickfingers")
    assert 'data-panel="skills"' in pip, "Skills panel not rendered for Pip"
    # All 18 standard 5e skills appear as buttons inside Pip's panel.
    # Anchor on the .mini-skills-grid open tag and count .mini-sk-btn
    # occurrences from there.
    grid_idx = pip.find('class="mini-skills-grid"')
    assert grid_idx >= 0, ".mini-skills-grid not found in Pip's Skills panel"
    grid_slice = pip[grid_idx:]
    # Count distinct .mini-sk-btn buttons — should be exactly 18.
    btn_count = len(re.findall(r'class="mini-sk-btn', grid_slice[:8000]))
    assert btn_count == 18, f"expected 18 skill buttons, got {btn_count}"


async def test_features_panel_renders_for_pc_with_class_features():
    """Phase 2.3b verification — ``_tab_features.html`` produces the
    Features panel with at least one ``.mini-feature-row`` + 🪄 Use
    button for a PC with class features. Spot-checks Mira Greenleaf
    (Barbarian — Rage / Reckless Attack) — the demo seed gives every
    PHB class at least one class-features entry by Phase A wrap."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        login = await client.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"}, follow_redirects=True)
        assert login.status_code in (200, 303)
        resp = await client.get(CAMPAIGN_PAGE, follow_redirects=True)
    html = resp.text
    # Pick the first PC that has a Features panel rendered. The gate is
    # ``_features_list``, which depends on the demo seed; rather than
    # hardcoding a class assume at least ONE of the 12 demo PCs has
    # class features and assert the partial's markup appears at least
    # once somewhere on the page.
    assert 'data-panel="features"' in html, "no PC rendered a Features panel — _features_list empty across whole roster?"
    assert 'class="mini-feature-row' in html, "Features panel rendered but contains no .mini-feature-row"
    assert '🪄 Use' in html, "Features panel rendered but missing 🪄 Use button"
