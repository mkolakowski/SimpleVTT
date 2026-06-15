"""v2.323.0 — Glamoured Studded Leather (RAW DMG p.172, rare, NO attunement):
"You gain a +1 bonus to AC while you wear this armor."

Pure substrate clone of v2.301.0 Elven Chain (same `ac_bonus: 1`, same no-
attunement contract, same studded-leather-themed flavor). Rides the existing
`ac_bonus` substrate the Cloak/Ring of Protection and Bracers of Defense
already feed into `_read_target_ac` — an equipped Glamoured Studded Leather
reads as `target_ac = base + 1` at attack hit-determination time, with zero
new engine code. The bonus-action illusory-disguise property is GM-narrated
in v1.

Carrier: Lyra Sunstrider (Bard) holds the suit as inert spare loot (the
v2.318.1 spare-loot precedent). Lyra already wears her seed Studded Leather
(`ac_value: 12`) + several +AC items, so the absolute AC isn't a clean
number to assert against — the tests measure the *delta*: read `target_ac`
with the suit inert, PATCH it equipped, read `target_ac` again, and assert
it rose by exactly 1. Krieger swings his greataxe to surface the target AC.
Restores Lyra's inventory on teardown.

Three tests mirror `test_item_elven_chain.py`:
  - Equipped grants +1 AC delta.
  - No-attunement contract (`attuned` flag stays False; bonus still applies).
  - Unequip drops the bonus.
"""
from .conftest import CAMPAIGN_ID

_GLAM_SLUG = "glamoured-studded-leather"


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


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _snapshot_inv(gm_client, char_id):
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    return [dict(it) if isinstance(it, dict) else it for it in inv]


async def _patch_item(gm_client, char_id, slug, *, equipped):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == slug:
            it["equipped"] = equipped
            found = True
    assert found, f"carrier has no {slug} item"
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    assert resp.status_code == 200, resp.text
    return snapshot


async def _restore(gm_client, char_id, snapshot):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": snapshot},
    )


async def _attack_target_ac(gm_client, attacker, target, target_tok):
    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": attacker["id"],
            "attack_index": 0,
            "target_combatant_id": target_tok,
            "target_character_id": target["id"],
            "target_name": target["name"],
            "override": True,
        },
    )
    assert atk.status_code == 200, atk.text
    return atk.json().get("target_ac")


async def test_glamoured_adds_one_to_target_ac(gm_client, roster):
    """Equipping the suit raises Lyra's target_ac by exactly 1 vs the inert
    baseline."""
    krieger = roster["Krieger Stonefist"]
    lyra = roster["Lyra Sunstrider"]
    lyra_tok = f"tok_glam_lyra_{lyra['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_glam_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": lyra["id"], "name": lyra["name"],
         "tok_id": lyra_tok, "hp_max": 44, "initiative": 8},
    ])
    snap = await _patch_item(gm_client, lyra["id"], _GLAM_SLUG, equipped=False)
    try:
        base_ac = await _attack_target_ac(gm_client, krieger, lyra, lyra_tok)
        await _patch_item(gm_client, lyra["id"], _GLAM_SLUG, equipped=True)
        worn_ac = await _attack_target_ac(gm_client, krieger, lyra, lyra_tok)
        assert base_ac is not None and worn_ac is not None, (
            f"target_ac missing: base={base_ac!r} worn={worn_ac!r}"
        )
        assert worn_ac == base_ac + 1, (
            f"expected +1 AC from Glamoured Studded Leather: "
            f"base={base_ac}, worn={worn_ac}"
        )
    finally:
        await _restore(gm_client, lyra["id"], snap)


async def test_glamoured_no_attunement_required(gm_client, roster):
    """The suit grants its +1 un-attuned — equipping it (attuned stays False
    in the seed) is enough to raise target_ac."""
    krieger = roster["Krieger Stonefist"]
    lyra = roster["Lyra Sunstrider"]
    lyra_tok = f"tok_glam_attune_lyra_{lyra['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_glam_attune_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": lyra["id"], "name": lyra["name"],
         "tok_id": lyra_tok, "hp_max": 44, "initiative": 8},
    ])
    snap = await _patch_item(gm_client, lyra["id"], _GLAM_SLUG, equipped=False)
    try:
        base_ac = await _attack_target_ac(gm_client, krieger, lyra, lyra_tok)
        await _patch_item(gm_client, lyra["id"], _GLAM_SLUG, equipped=True)
        inv = await _snapshot_inv(gm_client, lyra["id"])
        suit = next(
            it for it in inv
            if isinstance(it, dict) and it.get("_slug") == _GLAM_SLUG
        )
        assert not suit.get("attuned"), (
            f"suit should grant its +1 un-attuned, got: {suit!r}"
        )
        worn_ac = await _attack_target_ac(gm_client, krieger, lyra, lyra_tok)
        assert worn_ac == base_ac + 1, (
            f"expected +1 AC un-attuned: base={base_ac}, worn={worn_ac}"
        )
    finally:
        await _restore(gm_client, lyra["id"], snap)


async def test_glamoured_unequip_drops_bonus(gm_client, roster):
    """Equipping then unequipping returns target_ac to baseline."""
    krieger = roster["Krieger Stonefist"]
    lyra = roster["Lyra Sunstrider"]
    lyra_tok = f"tok_glam_drop_lyra_{lyra['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_glam_drop_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": lyra["id"], "name": lyra["name"],
         "tok_id": lyra_tok, "hp_max": 44, "initiative": 8},
    ])
    snap = await _patch_item(gm_client, lyra["id"], _GLAM_SLUG, equipped=False)
    try:
        base_ac = await _attack_target_ac(gm_client, krieger, lyra, lyra_tok)
        await _patch_item(gm_client, lyra["id"], _GLAM_SLUG, equipped=True)
        worn_ac = await _attack_target_ac(gm_client, krieger, lyra, lyra_tok)
        assert worn_ac == base_ac + 1, (base_ac, worn_ac)
        await _patch_item(gm_client, lyra["id"], _GLAM_SLUG, equipped=False)
        back_ac = await _attack_target_ac(gm_client, krieger, lyra, lyra_tok)
        assert back_ac == base_ac, (
            f"expected AC back to baseline after unequip: "
            f"base={base_ac}, back={back_ac}"
        )
    finally:
        await _restore(gm_client, lyra["id"], snap)
