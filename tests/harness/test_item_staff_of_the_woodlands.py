"""v2.358.0 — magic-items: Staff of the Woodlands (RAW DMG p.202, rare,
attunement by a druid). Bucket-B passive drop-in off the v2.344.5 triage.
The clean passive — "+2 bonus to spell attack rolls and to the saving
throw DCs of your druid spells" — wires the **+2 spell save DC** via the
new `spell_dc_bonus` substrate, folded into
`_compute_spell_save_dc_from_sheet` (the single source for the caster's
spell DC). The +2 quarterstaff is baked on the wielder's attack row; the
+2 spell ATTACK bonus, the 10 nature-spell charges, and the plant-a-tree
power are GM-narrated. RAW restricts the bonus to druid spells; v1
applies it to all the wielder's spells (Mira is a Druid).

Observability: Mira Greenleaf carries the staff as inert Armory's
Remainder loot AND a Staff of Swarming Insects whose Insect Plague action
resolves its save DC via the "spell" sentinel (= Mira's spell save DC,
baseline 14 = 8 + 3 prof + 3 WIS). So with the Woodlands staff PATCHed
equipped+attuned, Insect Plague's reported `save_dc` rises to 16. The
seed-inert + PATCH-in-test pattern keeps the demo's attunement count
unchanged.

Tests:
  - with the Woodlands staff equipped+attuned → Insect Plague save_dc=16.
  - control (Woodlands staff inert) → Insect Plague save_dc=14.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_WOODLANDS = "staff-of-the-woodlands"
_SWARMING = "staff-of-swarming-insects"


def _slug_index(inventory, slug):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == slug:
            return i
    return -1


def _mkc(cid, char_id=None, name="X", hp_max=200):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
        "ac": 1, "buffs": [], "creature_type": "humanoid",
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


async def _patch(gm_client, char_id, fields):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=fields,
    )


@pytest_asyncio.fixture
async def mira(roster):
    return roster["Mira Greenleaf"]


def _set_woodlands(inv, *, equipped, attuned):
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _WOODLANDS:
            it["equipped"], it["attuned"] = equipped, attuned
            found = True
    assert found, "Mira has no staff-of-the-woodlands item"
    return new_inv


def _full_swarming(resources):
    new_res = [dict(r) if isinstance(r, dict) else r for r in resources]
    for r in new_res:
        if isinstance(r, dict) and r.get("key") == _SWARMING:
            r["current"], r["max"] = 10, 10
    return new_res


async def _insect_plague_save_dc(gm_client, mira, idx, tag):
    a = f"tok_sotw_{tag}"
    await _seed_battle(gm_client, [
        _mkc(f"tok_sotw_mira_{mira['id']}_{tag}", mira["id"], name=mira["name"]),
        _mkc(a, None, name="Bandit"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-insect-plague",
            "target_combatant_ids": [a],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json().get("save_dc")


async def test_woodlands_boosts_spell_dc(gm_client, mira):
    """With the Staff of the Woodlands equipped+attuned, Mira's spell save
    DC rises +2 → Insect Plague (spell-DC sentinel) reports save_dc=16."""
    sheet = await _sheet(gm_client, mira["id"])
    inv = list(sheet.get("inventory") or [])
    res = list(sheet.get("resources") or [])
    inv_snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    res_snapshot = [dict(r) if isinstance(r, dict) else r for r in res]
    swarm_idx = _slug_index(inv, _SWARMING)
    assert swarm_idx >= 0, "Mira must carry a Staff of Swarming Insects"
    try:
        await _patch(gm_client, mira["id"], {
            "inventory": _set_woodlands(inv, equipped=True, attuned=True),
            "resources": _full_swarming(res),
        })
        dc = await _insect_plague_save_dc(gm_client, mira, swarm_idx, "boost")
        assert dc == 16, f"expected spell DC 14+2=16 with Woodlands staff; got {dc}"
    finally:
        await _patch(gm_client, mira["id"], {
            "inventory": inv_snapshot, "resources": res_snapshot,
        })


async def test_woodlands_inert_baseline_dc(gm_client, mira):
    """Control: with the Staff of the Woodlands inert (not attuned), Insect
    Plague reports the unmodified spell DC of 14 — proving the +2 is
    staff-sourced."""
    sheet = await _sheet(gm_client, mira["id"])
    inv = list(sheet.get("inventory") or [])
    res = list(sheet.get("resources") or [])
    inv_snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    res_snapshot = [dict(r) if isinstance(r, dict) else r for r in res]
    swarm_idx = _slug_index(inv, _SWARMING)
    assert swarm_idx >= 0, "Mira must carry a Staff of Swarming Insects"
    try:
        await _patch(gm_client, mira["id"], {
            "inventory": _set_woodlands(inv, equipped=False, attuned=False),
            "resources": _full_swarming(res),
        })
        dc = await _insect_plague_save_dc(gm_client, mira, swarm_idx, "base")
        assert dc == 14, f"expected unmodified spell DC 14; got {dc}"
    finally:
        await _patch(gm_client, mira["id"], {
            "inventory": inv_snapshot, "resources": res_snapshot,
        })
