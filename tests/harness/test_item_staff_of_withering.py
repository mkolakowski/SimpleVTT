"""v2.346.0 — magic-items: Staff of Withering (RAW DMG p.202, rare,
attunement cleric/druid/warlock). Bucket-C on-hit rider drop-in off the
v2.344.5 stub triage. The clean mechanical part reuses the Frost Brand
always-on dice-uplift: on a hit the wielder deals +2d10 necrotic via
``_MAGIC_ITEM_ATTACK_RIDERS["staff-of-withering"]`` (section 6c), surfaced
in the /attack response's ``auto_uplifts`` with source
``item-staff-of-withering``. RAW the +2d10 costs 1 of 3 charges and the
target makes a DC 15 CON save or has disadvantage on STR/CON checks +
saves for 1 hour — BOTH the charge limit AND the ability-drain save are
GM-narrated in v1 (the disadvantage rider needs the ``disadvantage_on``
intercept generalized beyond STR-checks-only; filed).

Demo fixture: Magnus Hexbinder (Warlock) carries the staff as inert spare
loot (equipped=False / attuned=False — the v2.344.0 Armory's Remainder
seed). The happy-path test PATCHes it equipped+attuned, attacks, and
asserts the +2d10 necrotic uplift; the attunement-gate test PATCHes it
equipped-but-unattuned and asserts the rider does NOT fire. Both restore
the seed inventory on teardown.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "staff-of-withering"


def _uplifts(data, source):
    return [u for u in (data.get("auto_uplifts") or [])
            if u.get("source") == source]


def _mkc(cid, char_id=None, name="X", ac=1):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 200, "hp_max": 200,
        "ac": ac,
        "buffs": [],
        "creature_type": "humanoid",
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _staff_attack_idx(gm_client, char_id):
    data = await _sheet_json(gm_client, char_id)
    attacks = (data.get("sheet") or {}).get("attacks") or []
    for i, a in enumerate(attacks):
        if isinstance(a, dict) and a.get("_slug") == _SLUG:
            return i
    raise AssertionError(f"Staff of Withering attack not found: {attacks!r}")


async def _patch_inventory(gm_client, char_id, inv):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": inv},
    )


def _set_staff(inv, *, equipped, attuned):
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _SLUG:
            it["equipped"], it["attuned"] = equipped, attuned
            found = True
    assert found, "Magnus has no staff-of-withering item"
    return new_inv


@pytest_asyncio.fixture
async def magnus(roster):
    return roster["Magnus Hexbinder"]


async def test_staff_of_withering_necrotic_rider_fires(gm_client, magnus):
    """Happy path: with the staff PATCHed equipped+attuned, attacking a
    target surfaces a +2d10 necrotic uplift (source item-staff-of-withering)."""
    data = await _sheet_json(gm_client, magnus["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = await _staff_attack_idx(gm_client, magnus["id"])
    try:
        await _patch_inventory(
            gm_client, magnus["id"], _set_staff(inv, equipped=True, attuned=True)
        )
        m_cid = f"tok_sow_magnus_{magnus['id']}"
        tgt_cid = "tok_sow_target"
        await _seed_battle(gm_client, [
            _mkc(m_cid, magnus["id"], name=magnus["name"]),
            _mkc(tgt_cid, None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": magnus["id"],
                "attack_index": idx,
                "target_combatant_id": tgt_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data2 = resp.json()
        assert data2["attack_name"] == "Staff of Withering"
        ups = _uplifts(data2, "item-staff-of-withering")
        assert len(ups) == 1, data2.get("auto_uplifts")
        rider = ups[0]
        assert rider["label"] == "Staff of Withering"
        assert rider["expression"] == "2d10"
        assert rider["damage_type"] == "necrotic"
        # Non-crit 2d10 → [2, 20]; crit-doubled 4d10 → [4, 40].
        assert 2 <= rider["total"] <= 40
    finally:
        await _patch_inventory(gm_client, magnus["id"], snapshot)


async def test_staff_of_withering_requires_attunement(gm_client, magnus):
    """Attunement gate: equipped-but-unattuned, the +2d10 necrotic rider
    does NOT fire. Restores the seed inventory on teardown."""
    data = await _sheet_json(gm_client, magnus["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = await _staff_attack_idx(gm_client, magnus["id"])
    try:
        await _patch_inventory(
            gm_client, magnus["id"], _set_staff(inv, equipped=True, attuned=False)
        )
        m_cid = f"tok_sow2_magnus_{magnus['id']}"
        tgt_cid = "tok_sow2_target"
        await _seed_battle(gm_client, [
            _mkc(m_cid, magnus["id"], name=magnus["name"]),
            _mkc(tgt_cid, None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": magnus["id"],
                "attack_index": idx,
                "target_combatant_id": tgt_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        ups = _uplifts(resp.json(), "item-staff-of-withering")
        assert ups == [], (
            f"unattuned Staff of Withering must not fire the necrotic rider; "
            f"got {ups!r}"
        )
    finally:
        await _patch_inventory(gm_client, magnus["id"], snapshot)
