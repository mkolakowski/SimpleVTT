"""v2.302.0 — Dwarven Plate (RAW DMG p.150, very rare, NO attunement):
"While wearing this armor, you gain a +2 bonus to AC."

Rides the same `ac_bonus` substrate the Elven Chain (v2.301.0) and the
Cloak/Ring of Protection feed into `_read_target_ac` — an equipped Dwarven
Plate reads as `target_ac = base + 2` at attack hit-determination time, with
zero new engine code. No attunement: its catalog payload omits
`requires_attunement`, so the +2 applies while merely equipped.

Carrier: Garrik Ironside (Fighter) holds the plate as inert spare loot
(equipped=False). Garrik carries no other `ac_bonus` item (his Dragon Scale
Mail's +1 AC is descriptive, not wired to the substrate), so the test measures
the *delta*: read `target_ac` with the plate inert, PATCH it equipped, read
again, and assert it rose by exactly 2. A goblin/NPC isn't needed — Krieger
swings his greataxe to surface the target AC. Restores Garrik's inventory on
teardown.
"""
from .conftest import CAMPAIGN_ID

_PLATE_SLUG = "dwarven-plate"


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


async def test_dwarven_plate_adds_two_to_target_ac(gm_client, roster):
    """Equipping the Dwarven Plate raises Garrik's target_ac by exactly 2 vs
    the inert baseline."""
    krieger = roster["Krieger Stonefist"]
    garrik = roster["Garrik Ironside"]
    garrik_tok = f"tok_dwarven_plate_garrik_{garrik['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_dwarven_plate_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": garrik["id"], "name": garrik["name"],
         "tok_id": garrik_tok, "hp_max": 85, "initiative": 8},
    ])
    snap = await _patch_item(gm_client, garrik["id"], _PLATE_SLUG, equipped=False)
    try:
        base_ac = await _attack_target_ac(gm_client, krieger, garrik, garrik_tok)
        await _patch_item(gm_client, garrik["id"], _PLATE_SLUG, equipped=True)
        worn_ac = await _attack_target_ac(gm_client, krieger, garrik, garrik_tok)
        assert base_ac is not None and worn_ac is not None, (
            f"target_ac missing: base={base_ac!r} worn={worn_ac!r}"
        )
        assert worn_ac == base_ac + 2, (
            f"expected +2 AC from Dwarven Plate: base={base_ac}, worn={worn_ac}"
        )
    finally:
        await _restore(gm_client, garrik["id"], snap)


async def test_dwarven_plate_no_attunement_required(gm_client, roster):
    """The plate grants its +2 un-attuned — equipping it (attuned stays False
    in the seed) is enough to raise target_ac."""
    krieger = roster["Krieger Stonefist"]
    garrik = roster["Garrik Ironside"]
    garrik_tok = f"tok_dwarven_plate_attune_garrik_{garrik['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_dwarven_plate_attune_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": garrik["id"], "name": garrik["name"],
         "tok_id": garrik_tok, "hp_max": 85, "initiative": 8},
    ])
    snap = await _patch_item(gm_client, garrik["id"], _PLATE_SLUG, equipped=False)
    try:
        base_ac = await _attack_target_ac(gm_client, krieger, garrik, garrik_tok)
        await _patch_item(gm_client, garrik["id"], _PLATE_SLUG, equipped=True)
        inv = await _snapshot_inv(gm_client, garrik["id"])
        plate = next(
            it for it in inv
            if isinstance(it, dict) and it.get("_slug") == _PLATE_SLUG
        )
        assert not plate.get("attuned"), (
            f"plate should grant its +2 un-attuned, got: {plate!r}"
        )
        worn_ac = await _attack_target_ac(gm_client, krieger, garrik, garrik_tok)
        assert worn_ac == base_ac + 2, (
            f"expected +2 AC un-attuned: base={base_ac}, worn={worn_ac}"
        )
    finally:
        await _restore(gm_client, garrik["id"], snap)


async def test_dwarven_plate_unequip_drops_bonus(gm_client, roster):
    """Equipping then unequipping the plate returns target_ac to baseline."""
    krieger = roster["Krieger Stonefist"]
    garrik = roster["Garrik Ironside"]
    garrik_tok = f"tok_dwarven_plate_drop_garrik_{garrik['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_dwarven_plate_drop_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": garrik["id"], "name": garrik["name"],
         "tok_id": garrik_tok, "hp_max": 85, "initiative": 8},
    ])
    snap = await _patch_item(gm_client, garrik["id"], _PLATE_SLUG, equipped=False)
    try:
        base_ac = await _attack_target_ac(gm_client, krieger, garrik, garrik_tok)
        await _patch_item(gm_client, garrik["id"], _PLATE_SLUG, equipped=True)
        worn_ac = await _attack_target_ac(gm_client, krieger, garrik, garrik_tok)
        assert worn_ac == base_ac + 2, (base_ac, worn_ac)
        await _patch_item(gm_client, garrik["id"], _PLATE_SLUG, equipped=False)
        back_ac = await _attack_target_ac(gm_client, krieger, garrik, garrik_tok)
        assert back_ac == base_ac, (
            f"expected AC back to baseline after unequip: "
            f"base={base_ac}, back={back_ac}"
        )
    finally:
        await _restore(gm_client, garrik["id"], snap)
