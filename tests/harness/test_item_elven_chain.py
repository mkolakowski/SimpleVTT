"""v2.301.0 — Elven Chain (RAW DMG p.150, rare, NO attunement): "You gain a
+1 bonus to AC while you wear this armor."

Rides the existing `ac_bonus` substrate the Cloak/Ring of Protection and
Bracers of Defense already feed into `_read_target_ac` — an equipped Elven
Chain reads as `target_ac = base + 1` at attack hit-determination time, with
zero new engine code. Unlike those wondrous items it needs NO attunement: its
catalog payload omits `requires_attunement`, so the +1 applies while merely
equipped.

Carrier: Pip Quickfingers (Rogue) holds the chain as inert spare loot
(equipped=False). Pip already wears a Cloak + Ring of Protection (+1/+1 each),
so her absolute AC isn't a clean number to assert against — instead the test
measures the *delta*: read `target_ac` with the chain inert, PATCH it equipped,
read `target_ac` again, and assert it rose by exactly 1. Krieger swings his
greataxe to surface the target AC. Restores Pip's inventory on teardown.
"""
from .conftest import CAMPAIGN_ID

_CHAIN_SLUG = "elven-chain"


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


async def test_elven_chain_adds_one_to_target_ac(gm_client, roster):
    """Equipping the Elven Chain raises Pip's target_ac by exactly 1 vs the
    inert baseline."""
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_elven_chain_pip_{pip['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_elven_chain_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": pip["id"], "name": pip["name"],
         "tok_id": pip_tok, "hp_max": 47, "initiative": 8},
    ])
    snap = await _patch_item(gm_client, pip["id"], _CHAIN_SLUG, equipped=False)
    try:
        base_ac = await _attack_target_ac(gm_client, krieger, pip, pip_tok)
        await _patch_item(gm_client, pip["id"], _CHAIN_SLUG, equipped=True)
        worn_ac = await _attack_target_ac(gm_client, krieger, pip, pip_tok)
        assert base_ac is not None and worn_ac is not None, (
            f"target_ac missing: base={base_ac!r} worn={worn_ac!r}"
        )
        assert worn_ac == base_ac + 1, (
            f"expected +1 AC from Elven Chain: base={base_ac}, worn={worn_ac}"
        )
    finally:
        await _restore(gm_client, pip["id"], snap)


async def test_elven_chain_no_attunement_required(gm_client, roster):
    """The chain grants its +1 un-attuned — equipping it (attuned stays False
    in the seed) is enough to raise target_ac."""
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_elven_chain_attune_pip_{pip['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_elven_chain_attune_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": pip["id"], "name": pip["name"],
         "tok_id": pip_tok, "hp_max": 47, "initiative": 8},
    ])
    snap = await _patch_item(gm_client, pip["id"], _CHAIN_SLUG, equipped=False)
    try:
        base_ac = await _attack_target_ac(gm_client, krieger, pip, pip_tok)
        await _patch_item(gm_client, pip["id"], _CHAIN_SLUG, equipped=True)
        inv = await _snapshot_inv(gm_client, pip["id"])
        chain = next(
            it for it in inv
            if isinstance(it, dict) and it.get("_slug") == _CHAIN_SLUG
        )
        assert not chain.get("attuned"), (
            f"chain should grant its +1 un-attuned, got: {chain!r}"
        )
        worn_ac = await _attack_target_ac(gm_client, krieger, pip, pip_tok)
        assert worn_ac == base_ac + 1, (
            f"expected +1 AC un-attuned: base={base_ac}, worn={worn_ac}"
        )
    finally:
        await _restore(gm_client, pip["id"], snap)


async def test_elven_chain_unequip_drops_bonus(gm_client, roster):
    """Equipping then unequipping the chain returns target_ac to baseline."""
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_elven_chain_drop_pip_{pip['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_elven_chain_drop_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": pip["id"], "name": pip["name"],
         "tok_id": pip_tok, "hp_max": 47, "initiative": 8},
    ])
    snap = await _patch_item(gm_client, pip["id"], _CHAIN_SLUG, equipped=False)
    try:
        base_ac = await _attack_target_ac(gm_client, krieger, pip, pip_tok)
        await _patch_item(gm_client, pip["id"], _CHAIN_SLUG, equipped=True)
        worn_ac = await _attack_target_ac(gm_client, krieger, pip, pip_tok)
        assert worn_ac == base_ac + 1, (base_ac, worn_ac)
        await _patch_item(gm_client, pip["id"], _CHAIN_SLUG, equipped=False)
        back_ac = await _attack_target_ac(gm_client, krieger, pip, pip_tok)
        assert back_ac == base_ac, (
            f"expected AC back to baseline after unequip: "
            f"base={base_ac}, back={back_ac}"
        )
    finally:
        await _restore(gm_client, pip["id"], snap)
