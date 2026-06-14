"""v2.270.0 — charged-items Phase 3: Gem of Seeing (RAW DMG p.171, rare,
attunement). The FIRST ``action_kind: "buff"`` charge action — the
``gaze`` action routes through the new ``_use_item_action_buff`` handler
instead of a catalogued spell cast (wand shape #1), an AoE save (staff
shape #2), or an attack roll (Ring of the Ram). It spends 1 of 3 charges
and installs the ``truesight`` buff template (60-ft truesight, 100 rounds
= 10 minutes) on the wielder's own combatant.

Demo fixture: Rowan Quickbow (Ranger) carries an equipped + attuned Gem
of Seeing + a 3-charge resource row at key ``gem-of-seeing``.

Tests:
  - happy path: gaze with Rowan in an active battle → ok, action_kind
    "buff", buff_key "truesight", charges_spent=1, buff_installed=True,
    duration_rounds=100, resource 3 → 2
  - drained gem (0 charges) → 409 insufficient_charges
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "gem-of-seeing"


def _mkc(cid, char_id=None, name="X", hp_max=200, ac=10):
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


async def _gem_inv_idx(gm_client, char_id):
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    inv = sheet.get("inventory") or []
    for i, it in enumerate(inv):
        if isinstance(it, dict) and it.get("_slug") == _SLUG:
            return i
    raise AssertionError("Rowan has no gem-of-seeing inventory item")


@pytest_asyncio.fixture
async def rowan(roster):
    return roster["Rowan Quickbow"]


@pytest_asyncio.fixture
async def rowan_full_gem(gm_client, rowan):
    """Force-reseed Rowan's Gem of Seeing to a full 3 charges, restoring
    the snapshot on teardown."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 3, "max": 3}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
        json={"resources": resources},
    )
    yield rowan
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_gem_of_seeing_gaze_installs_truesight(gm_client, rowan_full_gem):
    """Happy path: gaze with Rowan in an active battle → action_kind
    "buff", buff_key "truesight", charges_spent=1, buff_installed=True,
    duration_rounds=100, resource 3 → 2."""
    rowan = rowan_full_gem
    idx = await _gem_inv_idx(gm_client, rowan["id"])
    r_cid = f"tok_gos1_rowan_{rowan['id']}"
    await _seed_battle(gm_client, [
        _mkc(r_cid, rowan["id"], name=rowan["name"]),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "gaze",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["action_kind"] == "buff"
    assert data["buff_key"] == "truesight"
    assert data["charges_spent"] == 1
    assert data["buff_installed"] is True
    assert data["duration_rounds"] == 100
    assert data["resource"]["current"] == 2  # 3 → 2

    # The truesight buff lands on Rowan's combatant.
    battle_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    combatants = (
        ((battle_resp.json() or {}).get("battle") or {}).get("combatants") or []
    )
    me = next((c for c in combatants if c.get("id") == r_cid), None)
    assert me is not None
    keys = {b.get("key") for b in (me.get("buffs") or []) if isinstance(b, dict)}
    assert "truesight" in keys


async def test_gem_of_seeing_empty_returns_409(gm_client, rowan):
    """Drain the gem to 0 charges via /sheet-fields, then try to gaze →
    409 insufficient_charges."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    drained = [
        {**r, "current": 0} if (isinstance(r, dict) and r.get("key") == _SLUG) else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        idx = await _gem_inv_idx(gm_client, rowan["id"])
        r_cid = f"tok_gos2_rowan_{rowan['id']}"
        await _seed_battle(gm_client, [
            _mkc(r_cid, rowan["id"], name=rowan["name"]),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "gaze",
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 0
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"resources": snapshot},
        )
