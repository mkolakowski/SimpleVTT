"""v2.158.76 — magic-items-automation Phase 1b wiring for Ring of
Protection (rare ring, attunement: +1 AC, +1 saving throws).

Same mechanical shape as v2.158.74's Cloak of Protection — second
catalog entry in ``_MAGIC_ITEM_PASSIVES``. Tests use Tavik Stonebrow
(Cleric Lv 8) as the canary because:

  - Different PC from the Cloak fixture (Thalindra), so the two
    catalog entries' AC + save assertions don't interact.
  - Tavik's base AC is 18 (chain mail 16 + shield 2), so +1 ring
    pushes the test target to a clean integer.
  - Tavik's WIS save is Cleric-proficient (+3 WIS mod + +3 prof =
    +6), making the save-roll test exercise a meaningful save mod.

RAW (DMG p.191): Ring of Protection grants its bonus only while
attuned. The ``requires_attunement: true`` gate in the catalog +
walker (v2.158.74) enforces this.
"""
import pytest

from .conftest import CAMPAIGN_ID


async def _seed_battle_with(gm_client, char_specs: list[dict]) -> None:
    """Mirror of the helper in test_item_cloak_of_protection.py."""
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


async def test_ring_of_protection_grants_ac_bonus(gm_client, roster):
    """v2.158.76 Phase 1b AC half. Tavik wears an equipped + attuned
    Ring of Protection from the demo seed. Krieger swings his
    greataxe at him; ``target_ac`` should be base 18 + Ring +1 = 19.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]
    tavik_tok = f"tok_ring_ac_tavik_{tavik['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_ring_ac_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": tavik["id"], "name": tavik["name"],
         "tok_id": tavik_tok, "hp_max": 55, "initiative": 10},
    ])

    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "target_combatant_id": tavik_tok,
            "target_character_id": tavik["id"],
            "target_name": tavik["name"],
            "override": True,
        },
    )
    assert atk.status_code == 200, atk.text
    target_ac = atk.json().get("target_ac")
    # Tavik base AC 18 + Ring of Protection +1 = 19.
    assert target_ac == 19, (
        f"expected target_ac=19 (18 base + 1 Ring of Protection), "
        f"got {target_ac}; response={atk.json()}"
    )


async def test_ring_of_protection_grants_save_bonus(gm_client, roster):
    """v2.158.76 Phase 1b save half. Tavik rolls a WIS save (Cleric-
    proficient: +3 WIS mod + 3 prof = +6). The /roll endpoint
    detects ``stat_key='wis_save'``, walks his equipped items via
    ``_equipped_item_effects``, finds the Ring (+1 saves) and
    appends ``+1`` to the expression. The breakdown picks up the
    "Ring of Protection" attribution."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+6",
            "stat_key": "wis_save",
            "character_id": tavik["id"],
            "note": "WIS save (test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    breakdown = data.get("breakdown", "")
    assert "Ring of Protection" in breakdown, (
        f"expected 'Ring of Protection' in breakdown, got: {breakdown!r}"
    )
    assert "+1" in breakdown, (
        f"expected '+1' bonus annotation in breakdown, got: {breakdown!r}"
    )
