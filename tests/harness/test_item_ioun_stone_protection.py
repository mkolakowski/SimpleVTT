"""v2.228.0 — Ioun Stone of Protection (RAW DMG p.176, rare, attunement):
the first non-ability Ioun variant, and the first item to ride a per-
inventory-item AC override.

RAW: this dusty-rose prism orbits your head and grants +1 AC while
attuned. The SRD ships a single `ioun-stone` slug (whose catalog passive
carries an empty ability payload), so the Protection variant's AC bonus
rides the inventory item via `_ac_bonus` and wins over the catalog default
in `_equipped_item_effects` — the same per-item override pattern the giant
belt tiers (`_ability_set`) and ability ioun variants (`_ability_bonus`)
already use.

Demo fixture: Mira Greenleaf (Druid, base AC 15 = studded leather 12 +
DEX +3) wears an equipped + attuned Ioun Stone of Protection — her 3rd
attuned item (after the Vorpal Scimitar + Headband of Intellect, RAW max
3). So her combat AC is 16.
"""
from .conftest import CAMPAIGN_ID

_IOUN_SLUG = "ioun-stone"
_PROTECTION_NAME = "Ioun Stone of Protection"


async def _seed_battle_with(gm_client, char_specs: list[dict]) -> None:
    """Mirror of the helper in test_item_ring_of_protection.py."""
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


async def test_ioun_stone_protection_grants_ac_bonus(gm_client, roster):
    """Happy path: Mira wears an equipped + attuned Ioun Stone of
    Protection from the demo seed. Krieger swings his greataxe at her;
    ``target_ac`` should be base 15 + stone +1 = 16."""
    krieger = roster["Krieger Stonefist"]
    mira = roster["Mira Greenleaf"]
    mira_tok = f"tok_ioun_ac_mira_{mira['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_ioun_ac_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": mira["id"], "name": mira["name"],
         "tok_id": mira_tok, "hp_max": 36, "initiative": 10},
    ])

    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "target_combatant_id": mira_tok,
            "target_character_id": mira["id"],
            "target_name": mira["name"],
            "override": True,
        },
    )
    assert atk.status_code == 200, atk.text
    target_ac = atk.json().get("target_ac")
    assert target_ac == 16, (
        f"expected target_ac=16 (15 base + 1 Ioun Stone of Protection), "
        f"got {target_ac}; response={atk.json()}"
    )


async def test_ioun_stone_protection_unequip_reverts_ac(gm_client, roster):
    """Unequipping the stone reverts the +1 AC: Mira's ``target_ac`` drops
    back to her base 15. Restores the original inventory on teardown."""
    mira = roster["Mira Greenleaf"]
    krieger = roster["Krieger Stonefist"]
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-json",
    )
    inv = list((sheet_resp.json().get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict)
         and it.get("_slug") == _IOUN_SLUG
         and it.get("_ac_bonus")),
        None,
    )
    assert idx is not None, "Mira has no Ioun Stone of Protection item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
            json={"inventory": inv},
        )
        mira_tok = f"tok_ioun_off_mira_{mira['id']}"
        await _seed_battle_with(gm_client, [
            {"id": krieger["id"], "name": krieger["name"],
             "tok_id": f"tok_ioun_off_krieger_{krieger['id']}",
             "hp_max": 55, "initiative": 14},
            {"id": mira["id"], "name": mira["name"],
             "tok_id": mira_tok, "hp_max": 36, "initiative": 10},
        ])
        atk = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": mira_tok,
                "target_character_id": mira["id"],
                "target_name": mira["name"],
                "override": True,
            },
        )
        assert atk.status_code == 200, atk.text
        target_ac = atk.json().get("target_ac")
        assert target_ac == 15, (
            f"expected target_ac=15 (base, stone unequipped), got "
            f"{target_ac}; response={atk.json()}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
