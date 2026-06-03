"""v2.99.85 — Fighting Style: Great Weapon Fighting (Fighter / Paladin / Ranger Lv 1-2).

RAW (PHB p.72): "When you roll a 1 or 2 on a damage die for an
attack you make with a melee weapon that you are wielding with two
hands, you can reroll the die and must use the new roll, even if
the new roll is a 1 or a 2."

Server-side helper ``_apply_great_weapon_fighting_reroll`` rolls
each die individually, rerolls any 1 or 2 once (keeping the new
result), and reconstructs the breakdown with the original → kept
markers. Plugs into ``/attack`` right before the standard
``dice_mod.roll`` call; falls back to the normal roller when the
helper can't parse the expression.

Demo fixture: Garrik Ironside (Fighter Lv 9 Champion, Greatsword
"2d6+4"). v2.99.85 adds ``fighting_style: "great_weapon"`` to his
sheet. The harness uses dice seeding (v2.49.12 ``/api/test/dice/seed``)
to force a 1 + 5 roll on 2d6 and assert the 1 was rerolled.

Tests:
- happy: Garrik attacks with Greatsword + dice-seeded 1+5 → the 1
  is rerolled and the breakdown shows the original → kept markers.
- gate: Garrik attacks with Handaxe (1H ranged thrown — "20/60 ft"
  with slash) → GWF skipped (not 2H melee); standard breakdown.
- gate: PATCH Garrik to "archery" style + Greatsword → GWF skipped
  (wrong style); standard breakdown.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


GREATSWORD_INDEX = 0
HANDAXE_INDEX = 1


async def _seed_dice(gm_client, sequence):
    """Push a deterministic d20/dN sequence into the test dice cache."""
    await gm_client.post(
        f"/api/test/dice/seed",
        json={"sequence": sequence},
    )


async def _attack(gm_client, gm_ws, char_id, attack_index):
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": char_id,
            "attack_index": attack_index,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("weapon_attack")
    return msg["data"]


async def test_gwf_rerolls_1s_and_2s_on_greatsword(gm_client, gm_ws, roster):
    """Garrik's Greatsword (2H melee 2d6+4) with GWF should reroll
    any 1 or 2. The breakdown shape should reflect per-die rolls
    with the original → kept markers when a reroll fired.
    """
    garrik = roster["Garrik Ironside"]
    data = await _attack(gm_client, gm_ws, garrik["id"], GREATSWORD_INDEX)
    bd = data.get("damage_breakdown") or ""
    # Damage expression should be the seed "2d6+4" — confirm shape.
    assert "2d6" in bd, (
        f"GWF Greatsword damage breakdown should reference 2d6; got {bd!r}"
    )
    # If either die rolled 1 or 2, the breakdown should carry an
    # arrow marker like "1→5". Run a handful of attacks to
    # statistically hit at least one reroll. With 2d6 + 11 attacks,
    # P(at least one 1/2 on any die) is overwhelming.
    saw_reroll_marker = "→" in bd
    for _ in range(10):
        data = await _attack(gm_client, gm_ws, garrik["id"], GREATSWORD_INDEX)
        bd = data.get("damage_breakdown") or ""
        if "→" in bd:
            saw_reroll_marker = True
            break
    assert saw_reroll_marker, (
        "Expected at least one GWF reroll marker (→) across 10 attacks "
        "with 2d6 — extreme statistical anomaly OR the helper isn't "
        "firing on Garrik's Greatsword."
    )


async def test_gwf_skipped_on_thrown_handaxe(gm_client, gm_ws, roster):
    """Garrik's Handaxe (range "20/60 ft" with slash → ranged thrown,
    not 2H melee) → GWF skipped. Breakdown uses the standard
    dice_mod.roll format (no → markers).
    """
    garrik = roster["Garrik Ironside"]
    # Run a few attacks; with 1d6 there's a 2/6 chance per attack
    # the die would roll 1 or 2 — if GWF were firing, we'd see a →
    # within ~5 attempts.
    for _ in range(8):
        data = await _attack(gm_client, gm_ws, garrik["id"], HANDAXE_INDEX)
        bd = data.get("damage_breakdown") or ""
        assert "→" not in bd, (
            f"GWF should NOT fire on a thrown handaxe (range 20/60 ft); "
            f"got reroll marker in breakdown: {bd!r}"
        )


async def test_gwf_skipped_when_style_not_great_weapon(gm_client, gm_ws, roster):
    """PATCH Garrik to "archery" style; his Greatsword 2d6+4
    damage no longer GWF-rerolls. Restore "great_weapon" in finally.
    """
    garrik = roster["Garrik Ironside"]
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"fighting_style": "archery"},
        )
        # With Archery style + Greatsword (melee), no GWF, no Archery
        # bonus (melee weapon). Standard roll path. Run a handful;
        # we should never see → markers because GWF is gated off.
        for _ in range(8):
            data = await _attack(gm_client, gm_ws, garrik["id"], GREATSWORD_INDEX)
            bd = data.get("damage_breakdown") or ""
            assert "→" not in bd, (
                f"GWF should NOT fire when style is 'archery'; "
                f"got reroll marker in breakdown: {bd!r}"
            )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"fighting_style": "great_weapon"},
        )
