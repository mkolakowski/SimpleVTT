"""v2.158.78 — magic-items-automation Phase 1d: stacking validation.

RAW (DMG p.138-191) lets a PC wear multiple +AC/+save items in
distinct slots — Cloak of Protection (neck) + Ring of Protection
(finger) stack for cumulative +2 AC and +2 saves. Pip Quickfingers
(Rogue Lv 7, base AC 14, no existing magic-item assertions in the
test suite) gets BOTH in her demo seed inventory so the tests can
assert the catalog's per-payload accumulator works across same-shape
entries without dedup.

This closes Phase 1 of the magic-items-automation plan: catalog
scales additively (v2.158.74), gates handle per-payload shape
variance (v2.158.77), and now the accumulator handles same-shape
multiplicity. Phase 2 brings the attunement UI + 3-item RAW cap.
"""
import pytest

from .conftest import CAMPAIGN_ID


async def _seed_battle_with(gm_client, char_specs: list[dict]) -> None:
    combatants = []
    for spec in char_specs:
        combatants.append({
            "id": spec["tok_id"],
            "char_id": spec["id"],
            "name": spec["name"],
            "initiative": spec.get("initiative", 10),
            "hp_current": spec.get("hp_max", 40),
            "hp_max": spec.get("hp_max", 40),
            "buffs": [],
            "economy": {
                "action": False, "bonus": False, "reaction": False,
                "movement": 0,
            },
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants, "turn_index": 0, "round": 1,
            "active": True,
        },
    )


async def test_cloak_and_ring_stack_ac_bonus(gm_client, roster):
    """v2.158.78 Phase 1d AC stacking. Pip wears equipped + attuned
    Cloak (+1) + Ring (+1). Krieger swings; ``target_ac`` should be
    base 14 + 1 + 1 = 16. Proves the walker accumulates `ac_bonus`
    across multiple matched items without dedup."""
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_stack_ac_pip_{pip['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_stack_ac_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": pip["id"], "name": pip["name"],
         "tok_id": pip_tok, "hp_max": 47, "initiative": 8},
    ])
    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "target_combatant_id": pip_tok,
            "target_character_id": pip["id"],
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert atk.status_code == 200, atk.text
    target_ac = atk.json().get("target_ac")
    # Pip base AC 14 + Cloak +1 + Ring +1 = 16.
    assert target_ac == 16, (
        f"expected target_ac=16 (14 base + 1 Cloak + 1 Ring), "
        f"got {target_ac}; response={atk.json()}"
    )


async def test_cloak_and_ring_stack_save_bonus(gm_client, roster):
    """v2.158.78 Phase 1d save stacking. Pip rolls a DEX save (Rogue-
    proficient: +3 DEX mod + +3 prof = +6). The /roll endpoint walks
    the cloak + ring entries, sums their save_bonus (+1 each = +2),
    appends +2 to the expression, and annotates the breakdown with
    BOTH item sources joined by ' + '."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+6",
            "stat_key": "dex_save",
            "character_id": pip["id"],
            "note": "DEX save (test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    # Both source items appear in the annotation.
    assert "Cloak of Protection" in breakdown, (
        f"expected 'Cloak of Protection' in stacked save breakdown, "
        f"got: {breakdown!r}"
    )
    assert "Ring of Protection" in breakdown, (
        f"expected 'Ring of Protection' in stacked save breakdown, "
        f"got: {breakdown!r}"
    )
    # The accumulator summed both +1's → +2 attribution.
    assert "+2" in breakdown, (
        f"expected '+2' summed bonus annotation in breakdown, "
        f"got: {breakdown!r}"
    )
