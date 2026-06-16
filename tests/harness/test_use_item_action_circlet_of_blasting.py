"""v2.356.0 — magic-items: Circlet of Blasting (RAW DMG p.159, uncommon,
NO attunement) through the `/use_item_action` endpoint + the NEW
spell-ATTACK item-action handler `_use_item_action_spell_attack`. Unlike
the save-condition Wand of Fear handler, each "beam" is a ranged spell
attack: roll 1d20 + attack_bonus vs the target's AC, and on a hit roll
the damage dice. Circlet of Blasting casts Scorching Ray — 3 rays at a
fixed +5, 2d6 fire each — once per dawn.

Demo home: Zara Emberfire (Sorcerer), seeded equipped (no attunement)
with a `circlet-of-blasting` 1/dawn resource. Targets are AC-1 dummies so
every +5 ray hits (barring a natural 1); dice are seeded for
determinism. The item index + resource row are looked up by `_slug`/key.

Tests:
  - happy: 3 rays at AC-1 targets → attack_bonus 5, beams 3,
    charges_spent 1, resource 1 → 0, 3 results, ≥1 hit dealing fire damage.
  - empty circlet (current=0) → 409 insufficient_charges.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "circlet-of-blasting"


def _slug_index(inventory, slug):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == slug:
            return i
    return -1


def _mkc(cid, char_id=None, name="X", hp_max=200, ac=1):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_max, "hp_max": hp_max,
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


async def _seed_dice(gm_client, seed):
    r = await gm_client.post("/api/test/dice/seed", json={"seed": seed})
    assert r.status_code == 200, r.text


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


@pytest_asyncio.fixture
async def zara(roster):
    return roster["Zara Emberfire"]


@pytest_asyncio.fixture
async def zara_full_circlet(gm_client, zara):
    """Force-reseed Zara's Circlet of Blasting use counter to current=1 via
    /sheet-fields PATCH. Snapshot + restore on teardown. Yields the
    inventory index resolved by `_slug`."""
    sheet = await _sheet(gm_client, zara["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 1, "max": 1}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": resources},
    )
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Zara must carry a seeded Circlet of Blasting"
    yield {"char": zara, "idx": idx}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_circlet_scorching_ray_3_beams(gm_client, zara_full_circlet):
    """v2.356.0 happy path. Scorching Ray (3 rays) at three AC-1 dummies →
    200 with attack_bonus 5, beams 3, charges_spent 1, resource 1→0, 3
    results, ≥1 hit dealing fire damage."""
    zara = zara_full_circlet["char"]
    idx = zara_full_circlet["idx"]
    await _seed_dice(gm_client, 7)
    zara_cid = f"tok_cob1_zara_{zara['id']}"
    a, b, c = "tok_cob1_a", "tok_cob1_b", "tok_cob1_c"
    await _seed_battle(gm_client, [
        _mkc(zara_cid, zara["id"], name=zara["name"]),
        _mkc(a, None, name="Dummy A"),
        _mkc(b, None, name="Dummy B"),
        _mkc(c, None, name="Dummy C"),
    ])
    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-scorching-ray",
                "target_combatant_ids": [a, b, c],
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ok"] is True
        assert data["item_name"] == "Circlet of Blasting"
        assert data["attack_bonus"] == 5
        assert data["beams"] == 3
        assert data["damage_type"] == "fire"
        assert data["charges_spent"] == 1
        assert data["resource"]["current"] == 0  # 1 → 0
        results = data.get("results") or []
        assert len(results) == 3
        hits = [r for r in results if r.get("hit")]
        assert hits, f"expected ≥1 ray to hit AC-1 dummies; got {results!r}"
        assert sum(int(r.get("damage_dealt") or 0) for r in hits) > 0
        for r in results:
            assert r.get("target_ac") == 1
    finally:
        await _seed_dice(gm_client, None)


async def test_circlet_empty_returns_409(gm_client, zara):
    """v2.356.0: drain the circlet to 0 uses via /sheet-fields, then try to
    invoke → 409 insufficient_charges."""
    sheet = await _sheet(gm_client, zara["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Zara must carry a seeded Circlet of Blasting"
    drained = [
        {**r, "current": 0}
        if (isinstance(r, dict) and r.get("key") == _SLUG)
        else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        zara_cid = f"tok_cob2_zara_{zara['id']}"
        await _seed_battle(gm_client, [
            _mkc(zara_cid, zara["id"], name=zara["name"]),
            _mkc("tok_cob2_a", None, name="Dummy"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-scorching-ray",
                "target_combatant_ids": ["tok_cob2_a"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 0
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
            json={"resources": snapshot},
        )
