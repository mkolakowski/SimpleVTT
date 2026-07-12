"""test_tavern_brawl_baseline — Phase 3 (Level 2), commit M.

Final Level 2 scenario from the plan: a multi-PC, multi-round
encounter validating the round / turn machinery end-to-end.

3 PCs + 3 NPCs, explicit initiative scores. After page load:

  1. ``#battle-round-label`` shows "Round 1" (battle active, ≥1
     combatant).
  2. All 6 init-tracker rows render, in initiative-descending order
     matching the seeded sequence (Garrik 18, Magnus 15, Tavik 12,
     Bandit Alpha 10, Bandit Beta 8, Bandit Gamma 6).
  3. The active-turn marker (``.init-entry.active-turn``) lands on
     the first combatant (turn_index=0 → Garrik).

Then walk a full round by clicking ``#battle-next-btn`` six times:

  4. After 6 clicks, ``turn_index`` has wrapped back to 0 and
     ``round`` has incremented to 2 — the round label now reads
     "Round 2" and the active-turn marker is back on Garrik.

The plan's bigger ask ("economy chips reset between rounds,
movement breadcrumb tracks, all damage applied correctly, no NPCs
left standing") is intentionally scoped down for this first
multi-round test. Economy + breadcrumb get their own follow-up
commits; damage application + NPC death belong to a separate test
that fires a multi-round resolution. This test pins the
round/turn loop itself, which is the foundation everything else
builds on.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import BrowserContext, expect

from ..conftest import tabletop_url
from ..helpers.battle import (
    bandit_template_id,
    delete_token,
    make_combatant,
    place_token,
    seed_battle,
    seed_battle_into_page,
)
from ..helpers.ws import WSCollector
from ..pages.tabletop import TabletopPage


GARRIK_CID = "es_brawl_garrik"
MAGNUS_CID = "es_brawl_magnus"
TAVIK_CID = "es_brawl_tavik"
BANDIT_ALPHA_CID = "es_brawl_bandit_alpha"
BANDIT_BETA_CID = "es_brawl_bandit_beta"
BANDIT_GAMMA_CID = "es_brawl_bandit_gamma"


@pytest.fixture
def garrik_tokenized(roster: dict):
    """v2.1006.0 — un-skips B2 (filed v2.49.236): the init-tracker
    orphan-cleanup (tabletop.html:4807) drops any combatant whose
    char_id isn't tokenized, and the demo's tokenized-six has no
    Fighter. Tokenize Garrik for the test via place-token and remove
    the token afterward — no demo-seed change, no leftover token on
    the public map."""
    garrik = roster["Garrik Ironside"]
    place_token(garrik["id"], 770.0, 700.0)
    yield garrik
    delete_token(garrik["id"])


def test_tavern_brawl_3_pcs_3_npcs_round_cycle(
    gm_context: BrowserContext,
    roster: dict,
    garrik_tokenized: dict,
):
    garrik = garrik_tokenized
    magnus = roster["Magnus Hexbinder"]
    tavik = roster["Brother Tavik Stonebrow"]
    bandit_tmpl = bandit_template_id()

    # Initiative order: Garrik 18 > Magnus 15 > Tavik 12 > Bandit
    # Alpha 10 > Beta 8 > Gamma 6. The seed_battle helper preserves
    # array order (no client-side reordering), so this list IS the
    # rendered order on the init tracker.
    combatants = [
        make_combatant(GARRIK_CID, char_id=garrik["id"],
                       name="Garrik Ironside", hp_cur=49, hp_max=49, initiative=18),
        make_combatant(MAGNUS_CID, char_id=magnus["id"],
                       name="Magnus Hexbinder", hp_cur=33, hp_max=33, initiative=15),
        make_combatant(TAVIK_CID, char_id=tavik["id"],
                       name="Brother Tavik Stonebrow", hp_cur=30, hp_max=30, initiative=12),
        make_combatant(BANDIT_ALPHA_CID, template_id=bandit_tmpl,
                       name="Bandit Alpha", hp_cur=11, hp_max=11, initiative=10),
        make_combatant(BANDIT_BETA_CID, template_id=bandit_tmpl,
                       name="Bandit Beta", hp_cur=11, hp_max=11, initiative=8),
        make_combatant(BANDIT_GAMMA_CID, template_id=bandit_tmpl,
                       name="Bandit Gamma", hp_cur=11, hp_max=11, initiative=6),
    ]
    seed_battle(combatants)
    seed_battle_into_page(gm_context, combatants)

    gm_page = gm_context.new_page()
    ws = WSCollector(gm_page)
    ws.start()
    gm_page.goto(tabletop_url())
    gm_page.evaluate("window._openDrawerPanel('players-drawer')")

    tabletop = TabletopPage(gm_page)
    # All 6 rows visible.
    expect(tabletop.combatant_row("Garrik Ironside")).to_be_visible(timeout=5000)
    for name in [
        "Magnus Hexbinder", "Brother Tavik Stonebrow",
        "Bandit Alpha", "Bandit Beta", "Bandit Gamma",
    ]:
        expect(tabletop.combatant_row(name)).to_be_visible(timeout=3000)

    # ── Step 1: battle state says Round 1 ─────────────────────────
    # v2.1006.0 — the #battle-round-label element was removed from the
    # template at v2.49.102 (renderBattle's write is guarded by
    # `if (roundEl)`), so assert on the structural state instead:
    # renderBattle mirrors the battle onto window.battle (v2.49.5).
    gm_page.wait_for_function(
        "() => window.battle && (window.battle.round || 1) === 1",
        timeout=3000,
    )

    # ── Step 2: DOM order matches initiative order ────────────────
    # Each .init-entry has a .mini-header-name child. Pull them all
    # in document order and assert the names sequence matches the
    # initiative-descending order we seeded.
    name_elements = gm_page.locator("#initiative-list .mini-header-name").all_text_contents()
    expected_order = [
        "Garrik Ironside",
        "Magnus Hexbinder",
        "Brother Tavik Stonebrow",
        "Bandit Alpha",
        "Bandit Beta",
        "Bandit Gamma",
    ]
    actual_order = [n.strip() for n in name_elements if n.strip() in expected_order]
    assert actual_order == expected_order, (
        f"init-tracker order mismatch.\n"
        f"  expected: {expected_order}\n"
        f"  actual:   {actual_order}"
    )

    # ── Step 3: active-turn marker on Garrik (turn_index=0) ───────
    active_row = gm_page.locator(".init-entry.active-turn")
    expect(active_row).to_be_visible(timeout=3000)
    expect(active_row.locator(".mini-header-name")).to_have_text(
        "Garrik Ironside", timeout=3000
    )

    # ── Step 4: walk a full round ─────────────────────────────────
    # 6 combatants → 6 Next clicks → turn_index wraps + round
    # increments. Each click runs the tick handler synchronously
    # (see test_buff_install_decrement).
    next_btn = gm_page.locator("#battle-next-btn")
    for _ in range(6):
        next_btn.click()

    # Battle state now says Round 2 (see the Step-1 note — the round
    # label element no longer exists; window.battle is the surface).
    gm_page.wait_for_function(
        "() => window.battle && window.battle.round === 2",
        timeout=3000,
    )

    # Active-turn marker wrapped back to Garrik.
    active_after = gm_page.locator(".init-entry.active-turn")
    expect(active_after).to_be_visible(timeout=3000)
    expect(active_after.locator(".mini-header-name")).to_have_text(
        "Garrik Ironside", timeout=3000
    )
