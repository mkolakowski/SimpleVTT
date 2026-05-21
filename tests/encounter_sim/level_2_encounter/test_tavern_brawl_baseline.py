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

from playwright.sync_api import BrowserContext, expect

from ..conftest import tabletop_url
from ..helpers.battle import (
    bandit_template_id,
    make_combatant,
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


def test_tavern_brawl_3_pcs_3_npcs_round_cycle(
    gm_context: BrowserContext,
    roster: dict,
):
    garrik = roster["Garrik Ironside"]
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

    # ── Step 1: round label says "Round 1" ────────────────────────
    round_label = gm_page.locator("#battle-round-label")
    expect(round_label).to_have_text("Round 1", timeout=3000)

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

    # Round label now says "Round 2".
    expect(round_label).to_have_text("Round 2", timeout=3000)

    # Active-turn marker wrapped back to Garrik.
    active_after = gm_page.locator(".init-entry.active-turn")
    expect(active_after).to_be_visible(timeout=3000)
    expect(active_after.locator(".mini-header-name")).to_have_text(
        "Garrik Ironside", timeout=3000
    )
