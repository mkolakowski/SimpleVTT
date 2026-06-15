"""v2.349.0 — magic-items: Staff of Striking (RAW DMG p.202, very rare,
attunement). Bucket-C on-hit rider drop-in off the v2.344.5 stub triage.
The +3 to attack/damage is baked onto Magnus's weapon row; on a hit the
staff adds +1d6 force via ``_MAGIC_ITEM_ATTACK_RIDERS["staff-of-striking"]``
(the Frost Brand always-on dice-uplift, section 6c), surfaced in the
/attack response's ``auto_uplifts`` with source ``item-staff-of-striking``.
RAW the wielder may expend 1-3 of 10 charges for +1d6 force each; v1
models the 1-charge minimum and GM-narrates spending more + the
10-charge/dawn economy.

Demo fixture: Magnus Hexbinder carries the staff as inert spare loot
(equipped=False / attuned=False — the v2.344.0 Armory's Remainder seed).
The happy-path test PATCHes it equipped+attuned, attacks, and asserts the
+1d6 force uplift; the attunement-gate test asserts the rider does NOT
fire when equipped-but-unattuned. Both restore the seed inventory.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "staff-of-striking"


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
    raise AssertionError(f"Staff of Striking attack not found: {attacks!r}")


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
    assert found, "Magnus has no staff-of-striking item"
    return new_inv


@pytest_asyncio.fixture
async def magnus(roster):
    return roster["Magnus Hexbinder"]


async def test_staff_of_striking_force_rider_fires(gm_client, magnus):
    """Happy path: with the staff PATCHed equipped+attuned, attacking a
    target surfaces a +1d6 force uplift (source item-staff-of-striking)."""
    data = await _sheet_json(gm_client, magnus["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = await _staff_attack_idx(gm_client, magnus["id"])
    try:
        await _patch_inventory(
            gm_client, magnus["id"], _set_staff(inv, equipped=True, attuned=True)
        )
        m_cid = f"tok_sos_magnus_{magnus['id']}"
        tgt_cid = "tok_sos_target"
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
        assert data2["attack_name"] == "Staff of Striking"
        ups = _uplifts(data2, "item-staff-of-striking")
        assert len(ups) == 1, data2.get("auto_uplifts")
        rider = ups[0]
        assert rider["label"] == "Staff of Striking"
        assert rider["expression"] == "1d6"
        assert rider["damage_type"] == "force"
        # Non-crit 1d6 → [1, 6]; crit-doubled 2d6 → [2, 12].
        assert 1 <= rider["total"] <= 12
    finally:
        await _patch_inventory(gm_client, magnus["id"], snapshot)


async def test_staff_of_striking_requires_attunement(gm_client, magnus):
    """Attunement gate: equipped-but-unattuned, the +1d6 force rider does
    NOT fire. Restores the seed inventory on teardown."""
    data = await _sheet_json(gm_client, magnus["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = await _staff_attack_idx(gm_client, magnus["id"])
    try:
        await _patch_inventory(
            gm_client, magnus["id"], _set_staff(inv, equipped=True, attuned=False)
        )
        m_cid = f"tok_sos2_magnus_{magnus['id']}"
        tgt_cid = "tok_sos2_target"
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
        ups = _uplifts(resp.json(), "item-staff-of-striking")
        assert ups == [], (
            f"unattuned Staff of Striking must not fire the force rider; "
            f"got {ups!r}"
        )
    finally:
        await _patch_inventory(gm_client, magnus["id"], snapshot)
