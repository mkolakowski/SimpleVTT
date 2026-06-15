"""v2.304.0 — Demon Armor (RAW DMG p.158, very rare, attunement): "While
wearing this armor, you gain a +1 bonus to AC" (plus Abyssal speech, magic
clawed-gauntlet unarmed strikes, and the can't-doff curse — all GM-narrated).

Rides the same `ac_bonus` substrate the Dwarven Plate (v2.302.0) / Elven Chain
(v2.301.0) / Cloak of Protection feed into `_read_target_ac` — an equipped +
attuned Demon Armor reads as `target_ac = base + 1` at attack hit-determination
time, with zero new engine code. Unlike the Dwarven Plate / Elven Chain this
one IS attunement-gated: its payload carries `requires_attunement: True`, so
the per-payload attunement check in `_equipped_item_effects` drops the +1 when
worn-but-not-attuned.

Carrier: Dame Seraphine Vael (Vengeance Paladin) holds the armor as inert spare
loot (equipped=False/attuned=False). She carries no other `ac_bonus` item (her
Ring of Resistance is `_resistance_type`, her Scarab of Protection is
`spell_save_advantage`), so the test measures the *delta*: read `target_ac`
inert, PATCH it equipped+attuned, read again, assert it rose by exactly 1.
Krieger swings his greataxe to surface the target AC. Restores on teardown.
"""
from .conftest import CAMPAIGN_ID

_ARMOR_SLUG = "demon-armor"


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


async def _patch_item(gm_client, char_id, slug, *, equipped, attuned):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == slug:
            it["equipped"] = equipped
            it["attuned"] = attuned
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


async def test_demon_armor_adds_one_to_target_ac(gm_client, roster):
    """Equipping + attuning the Demon Armor raises Seraphine's target_ac by
    exactly 1 vs the inert baseline."""
    krieger = roster["Krieger Stonefist"]
    sera = roster["Dame Seraphine Vael"]
    sera_tok = f"tok_demon_armor_sera_{sera['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_demon_armor_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": sera["id"], "name": sera["name"],
         "tok_id": sera_tok, "hp_max": 80, "initiative": 8},
    ])
    snap = await _patch_item(
        gm_client, sera["id"], _ARMOR_SLUG, equipped=False, attuned=False)
    try:
        base_ac = await _attack_target_ac(gm_client, krieger, sera, sera_tok)
        await _patch_item(
            gm_client, sera["id"], _ARMOR_SLUG, equipped=True, attuned=True)
        worn_ac = await _attack_target_ac(gm_client, krieger, sera, sera_tok)
        assert base_ac is not None and worn_ac is not None, (
            f"target_ac missing: base={base_ac!r} worn={worn_ac!r}"
        )
        assert worn_ac == base_ac + 1, (
            f"expected +1 AC from Demon Armor: base={base_ac}, worn={worn_ac}"
        )
    finally:
        await _restore(gm_client, sera["id"], snap)


async def test_demon_armor_requires_attunement(gm_client, roster):
    """Attunement gate: equipped-but-not-attuned grants no +1 — the bonus only
    appears once attuned."""
    krieger = roster["Krieger Stonefist"]
    sera = roster["Dame Seraphine Vael"]
    sera_tok = f"tok_demon_armor_attune_sera_{sera['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_demon_armor_attune_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": sera["id"], "name": sera["name"],
         "tok_id": sera_tok, "hp_max": 80, "initiative": 8},
    ])
    snap = await _patch_item(
        gm_client, sera["id"], _ARMOR_SLUG, equipped=False, attuned=False)
    try:
        base_ac = await _attack_target_ac(gm_client, krieger, sera, sera_tok)
        # Equipped but NOT attuned — attunement gate should suppress the +1.
        await _patch_item(
            gm_client, sera["id"], _ARMOR_SLUG, equipped=True, attuned=False)
        unattuned_ac = await _attack_target_ac(
            gm_client, krieger, sera, sera_tok)
        assert unattuned_ac == base_ac, (
            f"expected no +1 while un-attuned: base={base_ac}, "
            f"unattuned={unattuned_ac}"
        )
        # Now attune — the +1 should appear.
        await _patch_item(
            gm_client, sera["id"], _ARMOR_SLUG, equipped=True, attuned=True)
        worn_ac = await _attack_target_ac(gm_client, krieger, sera, sera_tok)
        assert worn_ac == base_ac + 1, (
            f"expected +1 once attuned: base={base_ac}, worn={worn_ac}"
        )
    finally:
        await _restore(gm_client, sera["id"], snap)


async def test_demon_armor_unequip_drops_bonus(gm_client, roster):
    """Equip+attune then unequip returns target_ac to baseline."""
    krieger = roster["Krieger Stonefist"]
    sera = roster["Dame Seraphine Vael"]
    sera_tok = f"tok_demon_armor_drop_sera_{sera['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_demon_armor_drop_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": sera["id"], "name": sera["name"],
         "tok_id": sera_tok, "hp_max": 80, "initiative": 8},
    ])
    snap = await _patch_item(
        gm_client, sera["id"], _ARMOR_SLUG, equipped=False, attuned=False)
    try:
        base_ac = await _attack_target_ac(gm_client, krieger, sera, sera_tok)
        await _patch_item(
            gm_client, sera["id"], _ARMOR_SLUG, equipped=True, attuned=True)
        worn_ac = await _attack_target_ac(gm_client, krieger, sera, sera_tok)
        assert worn_ac == base_ac + 1, (base_ac, worn_ac)
        await _patch_item(
            gm_client, sera["id"], _ARMOR_SLUG, equipped=False, attuned=False)
        back_ac = await _attack_target_ac(gm_client, krieger, sera, sera_tok)
        assert back_ac == base_ac, (
            f"expected AC back to baseline after unequip: "
            f"base={base_ac}, back={back_ac}"
        )
    finally:
        await _restore(gm_client, sera["id"], snap)
