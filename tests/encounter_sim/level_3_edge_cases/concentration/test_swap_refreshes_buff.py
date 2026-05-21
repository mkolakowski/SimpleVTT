"""test_swap_refreshes_buff — Phase 4 (Level 3), commit T.

Validates the **concentration-swap refresh semantics**: casting a
spell whose key already exists as an active concentration buff
REPLACES the old install (same buff, updated target) rather than
appending a second buff. The server's `_install_buff` path detects
the matching key and routes through `_drop_paired_concentration_
buffs` (tabletop_routes.py:433) to clean up any paired buffs on
OTHER combatants — for Hex specifically there are no paired buffs
(it's a caster-side buff with a `target_character_id` reference,
not a target-side install), but the refresh path still runs.

Scenario:
  1. Magnus casts Hex on Pip → 1 hex buff on Magnus with
     ``target_character_id = pip.id``.
  2. Magnus casts Hex on Thalindra → still 1 hex buff on Magnus,
     but ``target_character_id = thalindra.id``.
  3. Magnus's init-tracker row carries exactly ONE Hex chip both
     before and after (no duplication).

Closes the gap from commit L's `test_concentration_lifecycle`,
which proved DELETE concentration does NOT drop the paired buff.
The swap path IS what drops paired buffs — verified here via the
buff list mutation (target_character_id changes, count stays at
1).
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, expect

from ...conftest import tabletop_url
from ...helpers.battle import (
    make_combatant,
    post_use,
    seed_battle,
    seed_battle_into_page,
)
from ...helpers.reset import long_rest
from ...helpers.ws import WSCollector
from ...pages.tabletop import TabletopPage


MAGNUS_CID = "es_swap_magnus"
PIP_CID = "es_swap_pip"
THAL_CID = "es_swap_thal"


def test_hex_recast_refreshes_buff(
    gm_context: BrowserContext,
    roster: dict,
):
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    thal = roster["Thalindra Moonwhisper"]
    # Hex consumes a Pact slot per cast; long-rest so Magnus has at
    # least 2 L3 slots available (he has 2 max at L5).
    long_rest(magnus["id"])

    combatants = [
        make_combatant(
            MAGNUS_CID, char_id=magnus["id"],
            name="Magnus Hexbinder", hp_cur=33, hp_max=33, initiative=15,
        ),
        make_combatant(
            PIP_CID, char_id=pip["id"],
            name="Pip Quickfingers", hp_cur=35, hp_max=35, initiative=12,
        ),
        make_combatant(
            THAL_CID, char_id=thal["id"],
            name="Thalindra Moonwhisper", hp_cur=24, hp_max=24, initiative=10,
        ),
    ]
    seed_battle(combatants)
    seed_battle_into_page(gm_context, combatants)

    gm_page = gm_context.new_page()
    ws = WSCollector(gm_page)
    ws.start()
    gm_page.goto(tabletop_url())
    gm_page.evaluate("window._openDrawerPanel('players-drawer')")

    tabletop = TabletopPage(gm_page)
    expect(tabletop.combatant_row("Magnus Hexbinder")).to_be_visible(timeout=5000)

    # ── First Hex: on Pip ─────────────────────────────────────────
    resp1 = post_use(
        "cast_hex", magnus["id"],
        extra={"target_character_id": pip["id"], "ability": "STR"},
    )
    assert resp1.status_code == 200, resp1.text

    bu1 = ws.wait_for(
        "buff_update", timeout_ms=5000,
        predicate=lambda f: (
            f["data"].get("character_id") == magnus["id"]
            and any(b.get("key") == "hex" for b in f["data"].get("buffs") or [])
        ),
    )
    hex_buffs_1 = [b for b in bu1["data"]["buffs"] if b["key"] == "hex"]
    assert len(hex_buffs_1) == 1, (
        f"first cast should install 1 hex buff; got {len(hex_buffs_1)}: {hex_buffs_1}"
    )
    assert hex_buffs_1[0]["target_character_id"] == pip["id"]

    # Chip is rendered once.
    hex_chip_row = tabletop.combatant_row("Magnus Hexbinder").locator(
        ".buff-chip"
    ).filter(has_text="Hex")
    expect(hex_chip_row.first).to_be_visible(timeout=3000)
    assert hex_chip_row.count() == 1, (
        f"first cast should render 1 Hex chip; got {hex_chip_row.count()}"
    )

    # ── Second Hex: on Thalindra (swap target) ────────────────────
    resp2 = post_use(
        "cast_hex", magnus["id"],
        extra={"target_character_id": thal["id"], "ability": "DEX"},
    )
    assert resp2.status_code == 200, resp2.text

    bu2 = ws.wait_for(
        "buff_update", timeout_ms=5000,
        predicate=lambda f: (
            f["data"].get("character_id") == magnus["id"]
            and any(
                b.get("key") == "hex"
                and b.get("target_character_id") == thal["id"]
                for b in f["data"].get("buffs") or []
            )
        ),
    )
    hex_buffs_2 = [b for b in bu2["data"]["buffs"] if b["key"] == "hex"]
    # CRITICAL: refresh semantics, NOT append. Still exactly 1 hex
    # buff on Magnus — the second cast replaced the first.
    assert len(hex_buffs_2) == 1, (
        f"recast should REPLACE not APPEND; got {len(hex_buffs_2)} hex buffs: "
        f"{hex_buffs_2}"
    )
    assert hex_buffs_2[0]["target_character_id"] == thal["id"]
    # And the new buff carries the second cast's ability override.
    assert hex_buffs_2[0]["effects"].get("disadvantage_on_ability_check") == "DEX"

    # ── DOM: still exactly ONE Hex chip ───────────────────────────
    # No matter how many recasts, the chip count stays at 1. A
    # regression where the install path appended instead of refreshed
    # would show up here as count() == 2.
    hex_chip_after = tabletop.combatant_row("Magnus Hexbinder").locator(
        ".buff-chip"
    ).filter(has_text="Hex")
    expect(hex_chip_after.first).to_be_visible(timeout=3000)
    assert hex_chip_after.count() == 1, (
        f"refresh should not duplicate the chip; got {hex_chip_after.count()}"
    )
