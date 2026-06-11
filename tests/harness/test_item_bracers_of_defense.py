"""v2.158.77 — magic-items-automation Phase 1c wiring for Bracers of
Defense (rare wondrous item, attunement: +2 AC ONLY while wearing no
armor and using no shield, RAW DMG p.155).

Different shape from Cloak (v2.158.74) + Ring (v2.158.76) — needs new
gate primitives in ``_equipped_item_effects``:

  - ``requires_no_armor: True``  → skipped if ``_pc_is_wearing_armor``.
  - ``requires_no_shield: True`` → skipped if ``_pc_is_wearing_shield``.

The walker checks gates per-payload (not per-item) so a future hybrid
item like Robe of the Archmagi can mix gated + ungated passives in
one entry.

Demo fixture: Kael Brightleaf (Monk Way of the Open Hand, Lv 7,
Unarmored Defense → base AC 16, no equipped armor / shield). With
the Bracers attuned + equipped: target_ac = 16 + 2 = 18.

The "Bracers suppressed by armor/shield" negative path waits for
Phase 2's attunement UI to land the proper sheet-PATCH plumbing; the
gate logic is exercised in the walker code (see
``_equipped_item_effects`` in ``app/routes/tabletop_routes.py``).
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


async def test_bracers_of_defense_grants_ac_bonus(gm_client, roster):
    """v2.158.77 Phase 1c AC half + gate. Kael wears equipped +
    attuned Bracers from the demo seed; he has no armor + no shield
    so both gates pass. Krieger swings; ``target_ac`` should be
    base 16 + Bracers +2 = 18."""
    krieger = roster["Krieger Stonefist"]
    kael = roster["Kael Brightleaf"]
    kael_tok = f"tok_bracers_ac_kael_{kael['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_bracers_ac_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": kael["id"], "name": kael["name"],
         "tok_id": kael_tok, "hp_max": 52, "initiative": 12},
    ])
    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "target_combatant_id": kael_tok,
            "target_character_id": kael["id"],
            "target_name": kael["name"],
            "override": True,
        },
    )
    assert atk.status_code == 200, atk.text
    target_ac = atk.json().get("target_ac")
    # Kael base AC 16 + Bracers +2 = 18.
    assert target_ac == 18, (
        f"expected target_ac=18 (16 base + 2 Bracers of Defense), "
        f"got {target_ac}; response={atk.json()}"
    )


async def test_bracers_grant_no_save_bonus(gm_client, roster):
    """v2.158.77 Phase 1c shape guard: Bracers grant ONLY AC, never
    saves. Kael rolls a DEX save (Monk-proficient: +4 DEX + 3 prof =
    +7). The /roll endpoint's *_save hook walks `_equipped_item_effects`
    and finds no save_bonus from the Bracers — breakdown should NOT
    contain a Bracers attribution.

    This is the symmetric guard to Cloak/Ring (which grant BOTH AC
    and saves); proves the per-payload key shape is respected and a
    pure-AC item doesn't leak into save rolls.
    """
    kael = roster["Kael Brightleaf"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+7",
            "stat_key": "dex_save",
            "character_id": kael["id"],
            "note": "DEX save (test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    assert "Bracers of Defense" not in breakdown, (
        f"Bracers grant ONLY AC, must not appear in save breakdown; "
        f"got: {breakdown!r}"
    )
